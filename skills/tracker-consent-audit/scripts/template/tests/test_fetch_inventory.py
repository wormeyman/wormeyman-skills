import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import fetch_inventory  # noqa: E402

ROUTES: dict[str, tuple[int, dict, bytes]] = {}
HITS: list[str] = []


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        HITS.append(self.path)
        status, headers, body = ROUTES.get(self.path, (404, {}, b'{"code":"rest_no_route"}'))
        self.send_response(status)
        for k, v in headers.items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


@pytest.fixture
def site(monkeypatch):
    server = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    monkeypatch.setenv("TRACKER_AUDIT_APP_PASSWORD", "abcd efgh")
    ROUTES.clear()
    HITS.clear()
    yield f"http://127.0.0.1:{server.server_port}"
    server.shutdown()


def run(tmp_path, site, *extra):
    return fetch_inventory.main([str(tmp_path), "--user", "admin", "--site", site, *extra])


def test_writes_inventory(tmp_path, site):
    ROUTES["/wp-json/tracker-audit/v1/inventory"] = (200, {}, b'{"hooks": {}, "options": {}}')
    assert run(tmp_path, site) == 0
    assert json.loads((tmp_path / "inventory.json").read_text()) == {"hooks": {}, "options": {}}


def test_falls_back_to_rest_route(tmp_path, site):
    ROUTES["/?rest_route=/tracker-audit/v1/inventory"] = (200, {}, b'{"hooks": {}}')
    assert run(tmp_path, site) == 0


def test_401_names_application_passwords(tmp_path, site, capsys):
    ROUTES["/wp-json/tracker-audit/v1/inventory"] = (401, {}, b'{"code":"rest_not_logged_in"}')
    assert run(tmp_path, site) == 1
    assert "Application Password" in capsys.readouterr().out


def test_410_says_expired(tmp_path, site, capsys):
    ROUTES["/wp-json/tracker-audit/v1/inventory"] = (410, {}, b'{"code":"tracker_audit_expired"}')
    assert run(tmp_path, site) == 1
    out = capsys.readouterr().out
    assert "expired" in out
    assert "timestamps" in out  # an upload that keeps the old file time looks expired


def test_403_names_firewalls_and_prints_the_code(tmp_path, site, capsys):
    ROUTES["/wp-json/tracker-audit/v1/inventory"] = (403, {}, b'{"code":"rest_forbidden","message":"x"}')
    assert run(tmp_path, site) == 1
    out = capsys.readouterr().out
    assert "not an administrator" in out and "firewall" in out
    assert "rest_forbidden" in out


def test_403_html_page_prints_no_code(tmp_path, site, capsys):
    ROUTES["/wp-json/tracker-audit/v1/inventory"] = (403, {}, b"<html>Access denied</html>")
    assert run(tmp_path, site) == 1
    assert "Error code" not in capsys.readouterr().out


def test_cut_short_names_the_callback(tmp_path, site, capsys):
    ROUTES["/wp-json/tracker-audit/v1/inventory"] = (200, {"X-Tracker-Audit-Current": "wp_footer my_plugin_fn"}, b"partial")
    assert run(tmp_path, site) == 1
    assert "wp_footer my_plugin_fn" in capsys.readouterr().out


def test_fatal_500_names_the_callback(tmp_path, site, capsys):
    ROUTES["/wp-json/tracker-audit/v1/inventory"] = (500, {"X-Tracker-Audit-Current": "wp_head broken_fn"}, b"<html>fatal</html>")
    assert run(tmp_path, site) == 1
    assert "wp_head broken_fn" in capsys.readouterr().out


def test_missing_password(tmp_path, site, monkeypatch, capsys):
    monkeypatch.delenv("TRACKER_AUDIT_APP_PASSWORD")
    assert run(tmp_path, site) == 2  # pytest's stdin is not a terminal, so no prompt
    assert "Application Password" in capsys.readouterr().out


def test_never_follows_a_redirect(tmp_path, site, capsys):
    # urllib would copy the Authorization header to the new host; the fetch must stop instead.
    ROUTES["/wp-json/tracker-audit/v1/inventory"] = (302, {"Location": site + "/elsewhere"}, b"")
    ROUTES["/elsewhere"] = (200, {}, b'{"stolen": true}')
    assert run(tmp_path, site) == 1
    assert "redirected" in capsys.readouterr().out
    assert not HITS.count("/elsewhere")
    assert not (tmp_path / "inventory.json").exists()


def test_refuses_plain_http(tmp_path, capsys):
    assert fetch_inventory.main([str(tmp_path), "--user", "admin", "--site", "http://example.com"]) == 2
    assert "HTTPS" in capsys.readouterr().out

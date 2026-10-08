# /// script
# requires-python = ">=3.12"
# ///
"""Fetch the tracker-audit-probe inventory and save it next to a browser run.

Upload tracker-audit-probe.php to wp-content/mu-plugins/ first, and create an
Application Password for an administrator (Users > Profile > Application Passwords).

  uv run scripts/fetch_inventory.py results/<run-id> --user <admin-username>

Type the Application Password at the prompt. Do not put it on the command line:
the shell keeps it in its history. (TRACKER_AUDIT_APP_PASSWORD is read if set,
for scripted local tests.)

The password is a full admin login. It is never sent over plain HTTP and never
sent across a redirect. When this succeeds, delete the probe file AND revoke the
Application Password.
"""

import argparse
import base64
import getpass
import json
import os
import ssl
import sys
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).parent))
from site_config import SITE  # noqa: E402

ROUTE = "tracker-audit/v1/inventory"
LOOPBACK = ("127.0.0.1", "localhost", "::1")
HINTS = {
    401: "WordPress did not accept the login. Check the username and Application Password. "
         "Security plugins (Wordfence, Solid Security) can turn Application Passwords off.",
    403: "That user is not an administrator.",
    404: "No probe route. Is tracker-audit-probe.php in wp-content/mu-plugins/?",
    410: "The probe expired (48 hours after upload). Delete it, and upload a fresh copy if you still need it.",
}


class NoRedirect(urllib.request.HTTPRedirectHandler):
    """urllib copies Authorization onto a redirected request, even to another host. Never follow."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None  # urllib then raises HTTPError with the 3xx status


def _ssl_context(cafile: str | None) -> ssl.SSLContext:
    # --cafile ADDS a root to the system roots; passing it to create_default_context would replace them.
    ctx = ssl.create_default_context()
    if cafile:
        ctx.load_verify_locations(cafile)
    return ctx


def fetch(url: str, user: str, password: str, cafile: str | None):
    token = base64.b64encode(f"{user}:{password}".encode()).decode()
    req = urllib.request.Request(url, headers={
        "Authorization": f"Basic {token}", "Accept": "application/json", "User-Agent": "tracker-consent-audit/1.0",
    })
    ctx = _ssl_context(cafile)
    opener = urllib.request.build_opener(NoRedirect, urllib.request.HTTPSHandler(context=ctx))
    try:
        with opener.open(req, timeout=180) as r:
            return r.status, r.headers, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.headers, e.read()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("run", help="results/<run-id> folder to write inventory.json into")
    ap.add_argument("--user", required=True, help="administrator username")
    ap.add_argument("--site", default=SITE, help="site URL (default: SITE in site_config.py)")
    ap.add_argument("--cafile", help="extra CA root to trust, e.g. DDEV's $(mkcert -CAROOT)/rootCA.pem")
    a = ap.parse_args(argv)

    site = a.site.rstrip("/")
    u = urlparse(site)
    if u.scheme != "https" and u.hostname not in LOOPBACK:
        print(f"Refusing {site!r}: the Application Password is only sent over HTTPS.")
        return 2
    password = os.environ.get("TRACKER_AUDIT_APP_PASSWORD", "")
    if not password and sys.stdin.isatty():
        password = getpass.getpass("Application Password (input hidden): ")
    if not password:
        print("No Application Password. Run this in a terminal and type it at the prompt, "
              "or set TRACKER_AUDIT_APP_PASSWORD for a scripted local test.")
        return 2

    status, headers, body = 0, {}, b""
    for url in (f"{site}/wp-json/{ROUTE}", f"{site}/?rest_route=/{ROUTE}"):
        status, headers, body = fetch(url, a.user, password, a.cafile)
        if status != 404:
            break  # a 404 at /wp-json/ can mean plain permalinks; try ?rest_route= once

    if 300 <= status < 400:
        print(f"HTTP {status}: the site redirected to {headers.get('Location', '?')}. The password is never "
              "sent across a redirect. If that address is right, run again with --site set to it.")
        return 1
    if status != 200:
        print(f"HTTP {status}: {HINTS.get(status, body[:300].decode(errors='replace'))}")
        if "X-Tracker-Audit-Current" in headers:  # a PHP fatal in a callback returns 500 with this header
            print(f"The last callback the probe ran was: {headers['X-Tracker-Audit-Current']}")
        return 1
    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        last = headers.get("X-Tracker-Audit-Current", "unknown")
        print(f"The response was cut short, not JSON. The last callback the probe ran was: {last}")
        return 1

    out = Path(a.run) / "inventory.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, indent=1))
    hooks = sum(len(v) for v in data.get("hooks", {}).values())
    print(f"{out}: {len(data.get('plugins', []))} plugins, {hooks} hooked callbacks, "
          f"{len(data.get('options', {}))} options with tracker IDs.")
    print("Now delete wp-content/mu-plugins/tracker-audit-probe.php and revoke the Application Password "
          "(Users > Profile > Application Passwords).")
    return 0


if __name__ == "__main__":
    sys.exit(main())

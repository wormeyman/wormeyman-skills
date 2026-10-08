import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import gpc_probe  # noqa: E402
from gpc_probe import compare, is_site_host, privacy_strings  # noqa: E402


def test_extracts_and_drops_placeholders():
    reqs = [
        {"url": "https://a.example/bid?gpp=DBABL~BVQqAAAAAgA.QA&gpp_sid=7"},
        {"url": "https://b.example/x?gpp=DBABL%7EBVQqAAAAAgA.QA"},
        {"url": "https://c.example/x?gpp=[GPP]&us_privacy=[US_PRIVACY]"},
        {"url": "https://d.example/x?us_privacy=1YN-"},
        {"url": "https://e.example/x?us_privacy=%5BUS_PRIVACY%5D&gpp=${GPP}"},
    ]
    got = privacy_strings(reqs)
    assert got["gpp"] == {"DBABL~BVQqAAAAAgA.QA"}
    assert got["us_privacy"] == {"1YN-"}


def test_bad_values_go_to_unparsed_not_decoded():
    reqs = [
        {"url": "https://a.example/x?gpp=null&us_privacy=null"},
        {"url": "https://a.example/x?gpp=%3Cgpp%3E"},
        {"url": "https://a.example/x?gpp=gpp_sid="},
    ]
    got = privacy_strings(reqs)
    assert got["gpp"] == set()
    assert got["us_privacy"] == set()
    assert got["unparsed"] == {"null", "<gpp>", "gpp_sid="}


def fake_fetch(plain=((200, b"A", False), (200, b"A", False)), gpc=(200, b"B", False)):
    calls = iter(plain)

    def fetch(url, gpc_flag):
        return gpc if gpc_flag else next(calls)

    return fetch


def test_compare_stable_difference_differs():
    r = compare("https://v.example/s.js", fake_fetch())
    assert r["comparable"] and r["differs"]
    assert not r["unstable"] and not r["status_mismatch"]


def test_compare_plain_bodies_differ_is_unstable_not_differs():
    r = compare("https://v.example/s.js", fake_fetch(plain=((200, b"A", False), (200, b"C", False))))
    assert r["unstable"] and not r["differs"]


def test_compare_failed_fetch_is_not_comparable():
    r = compare("https://v.example/s.js", fake_fetch(gpc=(0, b"", False)))
    assert not r["comparable"] and not r["differs"]


def test_compare_403_under_gpc_is_status_mismatch_not_differs():
    r = compare("https://v.example/s.js", fake_fetch(gpc=(403, b"no", False)))
    assert r["status_mismatch"] and not r["differs"]


def test_compare_truncated_is_not_comparable():
    r = compare("https://v.example/s.js", fake_fetch(plain=((200, b"A", True), (200, b"A", False))))
    assert not r["comparable"] and not r["differs"]


def test_site_match_is_by_label_not_suffix(monkeypatch):
    monkeypatch.setattr(gpc_probe, "SITE_HOST", "site.com")
    assert is_site_host("site.com")
    assert is_site_host("www.site.com")
    assert not is_site_host("evilsite.com")

# /// script
# requires-python = ">=3.12"
# ///
"""Check tracker-audit-probe.php against a throwaway local WordPress site.

Usage: uv run tests/probe/check_probe.py http://127.0.0.1:8781 \
         --admin-pass '<app password>' --subscriber-pass '<app password>' \
         [--cafile <CA bundle for an https site with a private CA>]
"""

import argparse
import base64
import json
import ssl
import sys
import urllib.error
import urllib.request

ROUTE = "/wp-json/tracker-audit/v1/inventory"
CTX: ssl.SSLContext | None = None  # set in main(); --cafile adds a private CA, certificate checks are never disabled
SECRETS = ("fixture-subscriber@example.com", "fixture-comment-secret", "fixture-commenter@example.com",
           "fixture-admin@example.com", "<script>gtag")  # the raw option value, not its matched ID


def get(site: str, user: str | None = None, password: str | None = None):
    headers = {"Accept": "application/json"}
    if user:
        headers["Authorization"] = "Basic " + base64.b64encode(f"{user}:{password}".encode()).decode()
    req = urllib.request.Request(site + ROUTE, headers=headers)
    try:
        with urllib.request.urlopen(req, context=CTX, timeout=60) as r:
            return r.status, dict(r.headers), r.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), e.read().decode()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("site")
    ap.add_argument("--admin-pass", required=True)
    ap.add_argument("--subscriber-pass", required=True)
    ap.add_argument("--expect", choices=("ok", "expired", "exit"), default="ok")
    ap.add_argument("--cafile", default=None, help="CA bundle for an https site; omit for http or a publicly trusted certificate")
    a = ap.parse_args()
    global CTX
    CTX = ssl.create_default_context(cafile=a.cafile) if a.cafile else ssl.create_default_context()
    fails = []

    status, _, _ = get(a.site)
    if status != 401:
        fails.append(f"no login: expected 401, got {status}")
    status, _, _ = get(a.site, "subscriber", a.subscriber_pass)
    if status != 403:
        fails.append(f"subscriber: expected 403, got {status}")

    status, headers, body = get(a.site, "admin", a.admin_pass)
    if a.expect == "expired":
        if status != 410:
            fails.append(f"aged file: expected 410, got {status}")
    elif a.expect == "exit":
        current = headers.get("X-Tracker-Audit-Current", "")
        if "wp_footer" not in current:
            fails.append(f"exit: expected X-Tracker-Audit-Current naming wp_footer, got {current!r}")
    else:
        if status != 200:
            fails.append(f"admin: expected 200, got {status}: {body[:200]}")
        else:
            inv = json.loads(body)
            head = inv["hooks"]["wp_head"]
            gtag = [c for c in head if "G-FIXTURE123" in json.dumps(c.get("prints", {}))]
            if not gtag or gtag[0]["owner"] != "plugin:fixture-tracker":
                fails.append(f"wp_head gtag not attributed to plugin:fixture-tracker: {gtag}")
            elif "www.googletagmanager.com" not in gtag[0]["prints"]["domains"]:
                fails.append(f"protocol-relative URL not turned into a host: {gtag[0]['prints']}")
            enq = [c for c in inv["hooks"]["wp_enqueue_scripts"] if c.get("enqueued", {}).get("fixture-pixel")]
            if not enq or enq[0]["owner"] != "plugin:fixture-tracker":
                fails.append(f"enqueued fixture-pixel not attributed: {enq}")
            if inv["options"].get("fixture_header_scripts", {}).get("ga4") != ["G-OPTION4567"]:
                fails.append(f"option scan missed G-OPTION4567: {inv['options']}")
            leaked = [s for s in SECRETS if s in body]
            if leaked:
                fails.append(f"private data in the response: {leaked}")
            if headers.get("Cache-Control", "").find("no-store") < 0:
                fails.append(f"missing Cache-Control: no-store: {headers.get('Cache-Control')}")

    for f in fails:
        print("FAIL", f)
    print("ok" if not fails else f"{len(fails)} failure(s)")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())

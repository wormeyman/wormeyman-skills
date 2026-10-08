# /// script
# requires-python = ">=3.12"
# ///
"""What Global Privacy Control actually changes, beyond request counts.

1. Decodes every GPP and us_privacy string the ad code sent, in the plain run
   and in the GPC run, so "the ad network honors GPC" is a recorded fact.
2. Fetches each script the site's own vendors served, with and without the
   Sec-GPC: 1 header, and flags any that answer differently. Microsoft Clarity
   returns a one-line stub instead of its recorder when GPC is on.
3. Fetches /.well-known/gpc.json.

Usage:  uv run scripts/gpc_probe.py results/<run-id>
Writes: results/<run-id>/gpc-probe.json
"""

import hashlib
import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import unquote, urlparse

sys.path.insert(0, str(Path(__file__).parent))
from analyze import reg_domain  # noqa: E402
from gpp import decode, decode_usp  # noqa: E402
from site_config import SITE, SITE_HOST, SITE_VENDORS  # noqa: E402

UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/155.0.0.0 Safari/537.36"
MAX_SCRIPTS = 40


def privacy_strings(requests: list[dict]) -> dict[str, set[str]]:
    out: dict[str, set[str]] = {"gpp": set(), "us_privacy": set()}
    for r in requests:
        for key in out:
            for m in re.finditer(rf"[?&;]{key}=([^&;#]+)", r["url"]):
                value = unquote(m.group(1))
                if value and not value.startswith(("[", "$", "{")):
                    out[key].add(value)
    return out


def get(url: str, gpc: bool) -> tuple[int, bytes]:
    headers = {"User-Agent": UA, "Accept": "*/*"}
    if gpc:
        headers["Sec-GPC"] = "1"
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=30) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()
    except urllib.error.URLError:
        return 0, b""


def decoded(strings: set[str], fn) -> dict:
    out = {}
    for s in sorted(strings):
        try:
            out[s] = fn(s)
        except ValueError as err:
            out[s] = {"error": str(err)}
    return out


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    run = Path(argv[0])
    runs = {s: [r for f in sorted(run.glob(f"{s}-*-requests.json")) for r in json.loads(f.read_text())]
            for s in ("fresh", "gpc")}
    plain, with_gpc = privacy_strings(runs["fresh"]), privacy_strings(runs["gpc"])

    scripts = []
    for r in runs["fresh"]:
        host = urlparse(r["url"]).hostname or ""
        if r.get("type") == "script" and not host.endswith(SITE_HOST) and reg_domain(host) in SITE_VENDORS:
            if r["url"] not in scripts:
                scripts.append(r["url"])
    responses = []
    for url in scripts[:MAX_SCRIPTS]:
        (s1, b1), (s2, b2) = get(url, False), get(url, True)
        responses.append({
            "url": url, "plain_status": s1, "gpc_status": s2, "plain_bytes": len(b1), "gpc_bytes": len(b2),
            "differs": hashlib.sha256(b1).digest() != hashlib.sha256(b2).digest(),
        })

    status, body = get(SITE.rstrip("/") + "/.well-known/gpc.json", False)
    result = {
        "gpp_plain": decoded(plain["gpp"], decode), "gpp_gpc": decoded(with_gpc["gpp"], decode),
        "usp_plain": decoded(plain["us_privacy"], decode_usp), "usp_gpc": decoded(with_gpc["us_privacy"], decode_usp),
        "script_responses": responses,
        "gpc_json": {"status": status, "body": body[:500].decode(errors="replace")},
    }
    (run / "gpc-probe.json").write_text(json.dumps(result, indent=1))
    changed = [r["url"] for r in responses if r["differs"]]
    print(f"GPP strings: {len(plain['gpp'])} plain, {len(with_gpc['gpp'])} with GPC. "
          f"Site-vendor scripts that change with Sec-GPC: {len(changed)} of {len(responses)}. gpc.json: HTTP {status}.")
    for url in changed:
        print("  differs:", url[:120])
    return 0


if __name__ == "__main__":
    sys.exit(main())

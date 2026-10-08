# /// script
# requires-python = ">=3.12"
# ///
"""What Global Privacy Control actually changes, beyond request counts.

1. Decodes every GPP and us_privacy string the ad code sent, in the plain run
   and in the GPC run, so "the ad network honors GPC" is a recorded fact.
   Values that do not match the expected format are listed, never decoded.
2. Fetches each script the site's own vendors served, twice without the
   Sec-GPC: 1 header and once with it. A script counts as "differs" only when
   both plain fetches agree and the GPC body is different. Microsoft Clarity
   returns a one-line stub instead of its recorder when GPC is on.
3. Fetches /.well-known/gpc.json.

Usage:  uv run scripts/gpc_probe.py results/<run-id>
Writes: results/<run-id>/gpc-probe.json
"""

import http.client
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
MAX_BYTES = 5_000_000
GPP_RE = re.compile(r"D[A-Za-z0-9_-]{3,}(~[A-Za-z0-9_.-]+)+")
US_RE = re.compile(r"[0-9][YNyn-]{3}")
FORMATS = {"gpp": GPP_RE, "us_privacy": US_RE}


def privacy_strings(requests: list[dict]) -> dict[str, set[str]]:
    out: dict[str, set[str]] = {"gpp": set(), "us_privacy": set(), "unparsed": set()}
    for r in requests:
        for key, fmt in FORMATS.items():
            for m in re.finditer(rf"[?&;]{key}=([^&;#]+)", r["url"]):
                value = unquote(m.group(1))
                (out[key] if fmt.fullmatch(value) else out["unparsed"]).add(value)
    return out


def is_site_host(host: str) -> bool:
    return host == SITE_HOST or host.endswith("." + SITE_HOST)


def get(url: str, gpc: bool) -> tuple[int, bytes, bool]:
    """Return (status, body, truncated). Status 0 means no response."""
    headers = {"User-Agent": UA, "Accept": "*/*"}
    if gpc:
        headers["Sec-GPC"] = "1"
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=30) as r:
            body = r.read(MAX_BYTES + 1)
            return r.status, body[:MAX_BYTES], len(body) > MAX_BYTES
    except urllib.error.HTTPError as e:
        try:
            body = e.read(MAX_BYTES + 1)
        except (OSError, http.client.HTTPException):
            body = b""
        return e.code, body[:MAX_BYTES], len(body) > MAX_BYTES
    except (OSError, http.client.HTTPException):
        return 0, b"", False


def compare(url: str, fetch) -> dict:
    """Fetch plain twice and GPC once, then classify. fetch(url, gpc) -> (status, body, truncated)."""
    s1, b1, t1 = fetch(url, False)
    s2, b2, t2 = fetch(url, False)
    s3, b3, t3 = fetch(url, True)
    comparable = all(s == 200 for s in (s1, s2, s3)) and not (t1 or t2 or t3)
    unstable = differs = False
    basis = None
    if comparable and b1 == b2:
        # Stable plain body: an exact byte difference under GPC is a real change.
        differs = b1 != b3
        basis = "exact" if differs else None
    elif comparable:
        # Plain bodies differ between fetches (per-request values such as an ID).
        # Call it a real GPC change only when the plain lengths agree, and the GPC
        # body is far shorter than them, and the gap is not small.
        L1, L2 = len(b1), len(b2)
        m = (L1 + L2) / 2
        plain_close = abs(L1 - L2) <= 0.05 * max(L1, L2, 1)
        gap = abs(len(b3) - m)
        if plain_close and gap > 0.5 * m and gap >= 100:
            differs, basis = True, "size"
        else:
            unstable = True
    return {
        "url": url, "plain_status": s1, "gpc_status": s3,
        "plain_bytes": len(b1), "gpc_bytes": len(b3),
        "comparable": comparable, "unstable": unstable, "differs": differs,
        "basis": basis, "status_mismatch": s1 != s3,
    }


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
        if r.get("type") == "script" and not is_site_host(host) and reg_domain(host) in SITE_VENDORS:
            if r["url"] not in scripts:
                scripts.append(r["url"])
    responses = [compare(url, get) for url in scripts[:MAX_SCRIPTS]]

    status, body, _ = get(SITE.rstrip("/") + "/.well-known/gpc.json", False)
    result = {
        "gpp_plain": decoded(plain["gpp"], decode), "gpp_gpc": decoded(with_gpc["gpp"], decode),
        "usp_plain": decoded(plain["us_privacy"], decode_usp), "usp_gpc": decoded(with_gpc["us_privacy"], decode_usp),
        "unparsed_plain": sorted(plain["unparsed"]), "unparsed_gpc": sorted(with_gpc["unparsed"]),
        "script_responses": responses,
        "scripts_total": len(scripts), "scripts_skipped": max(0, len(scripts) - MAX_SCRIPTS),
        "gpc_json": {"status": status, "body": body[:500].decode(errors="replace")},
    }
    (run / "gpc-probe.json").write_text(json.dumps(result, indent=1))

    differs = [r["url"] for r in responses if r["differs"]]
    unstable = [r["url"] for r in responses if r["unstable"]]
    not_comparable = [r["url"] for r in responses if not r["comparable"] and not r["unstable"]]
    print(f"GPP strings: {len(plain['gpp'])} plain, {len(with_gpc['gpp'])} with GPC. "
          f"Site-vendor scripts that differ with Sec-GPC: {len(differs)} of {len(responses)} compared. "
          f"Scripts found: {len(scripts)}, skipped beyond MAX_SCRIPTS: {result['scripts_skipped']}. "
          f"gpc.json: HTTP {status}.")
    for r in responses:
        if r["differs"]:
            print(f"  differs ({r['basis']}): {r['url'][:120]}")
    print(f"Unstable (plain fetches disagree, not counted as differs): {len(unstable)}")
    for url in unstable:
        print("  unstable:", url[:120])
    print(f"Not comparable (failed or truncated fetch): {len(not_comparable)}")
    for url in not_comparable:
        print("  not comparable:", url[:120])
    return 0


if __name__ == "__main__":
    sys.exit(main())

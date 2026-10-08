# /// script
# requires-python = ">=3.12"
# ///
"""Build report/index.html (the page for the client) from report/template.html and a run.

Fills in the list of every outside domain seen in the plain-visit run.
Re-run after fixes with the new results folder.

Usage:  uv run scripts/build_report.py results/<run-id>
"""

import html
import json
import sys
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).parent))
from analyze import AD_NETWORK, SITE_HOST, SITE_VENDORS, label, reg_domain  # noqa: E402

HERE = Path(__file__).resolve().parent.parent  # project root


def outside_domains(run: Path) -> list[tuple[str, str]]:
    """(domain, readable name) for every outside domain in the plain-visit run."""
    seen = {}
    for f in run.glob("fresh-*-requests.json"):
        for r in json.loads(f.read_text()):
            host = urlparse(r["url"]).hostname or ""
            # Chrome extension ids and other non-web hosts have no dot.
            if not host or "." not in host or host == SITE_HOST or host.endswith("." + SITE_HOST):
                continue
            dom = reg_domain(host)
            if dom not in SITE_VENDORS:
                seen[dom] = label(dom)[0]
    return sorted(seen.items())


def main() -> None:
    run = Path(sys.argv[1])
    doms = outside_domains(run)
    chips = "".join(
        f'<span title="{html.escape(name)}">{html.escape(dom)}</span>' for dom, name in doms
    )
    block = (
        f"<details><summary>All {len(doms)} ad-related domains seen in the plain-visit test "
        f"({html.escape(AD_NETWORK)} and its partners)</summary>"
        f'<div class="chips">{chips}</div></details>'
    )
    page = (HERE / "report" / "template.html").read_text()
    assert "<!--DOMAINS-->" in page
    page = page.replace("<!--DOMAINS-->", block)
    (HERE / "report" / "index.html").write_text(page)
    print(f"report/index.html: {len(doms)} domains, {len(page):,} bytes")


if __name__ == "__main__":
    main()

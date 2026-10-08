# /// script
# requires-python = ">=3.12"
# ///
"""Scaffold a self-contained tracker and consent audit folder for one site.

Usage:  uv run new_audit.py https://www.example.com ~/Projects/example-privacy-audit \
          --ad-network Mediavine --name "Example Blog"

The folder gets its own copy of every script, so a re-test months later runs
the same code as the first audit even if this skill has changed since.
"""

import argparse
import re
import secrets
import shutil
import subprocess
import sys
from datetime import date
from pathlib import Path
from urllib.parse import urlparse

TEMPLATE = Path(__file__).resolve().parent / "template"
FILLED = ("scripts/site_config.py", "deploy/cloudflare.config.ts", "deploy/package.json",
          "README.md", "report/template.html")


ORIGIN = re.compile(r"https://[a-z0-9.-]+\.[a-z]{2,}/?")
NAME = re.compile(r"[A-Za-z0-9 &'.,-]{1,60}")


def scaffold(site: str, dest: Path, ad_network: str, site_name: str) -> Path:
    # Values go into Python, TypeScript, JSON and HTML files, so only plain values pass.
    if not ORIGIN.fullmatch(site):
        raise SystemExit(f"site must be a bare https:// origin like https://www.example.com, got {site!r}")
    if not NAME.fullmatch(site_name):
        raise SystemExit(f"name may use letters, digits, spaces and & ' . , - (60 at most), got {site_name!r}")
    u = urlparse(site)
    if dest.exists() and any(dest.iterdir()):
        raise SystemExit(f"{dest} exists and is not empty")
    shutil.copytree(TEMPLATE, dest, dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns("__pycache__", ".uv-cache", "node_modules", ".cloudflare",
                                              ".pytest_cache", ".ruff_cache", ".DS_Store", "dist", ".wrangler"))
    values = {
        "__SITE__": site.rstrip("/"),
        "__SITE_HOST__": u.hostname.removeprefix("www."),
        "__AD_NETWORK__": ad_network,
        "__CANARY__": f"audit-canary-{secrets.token_hex(2)}@example.com",
        "__WORKER_NAME__": f"wm-{secrets.token_hex(3)}",
        "__SITE_NAME__": site_name,
        "__DATE__": date.today().isoformat(),
    }
    for rel in FILLED:
        f = dest / rel
        text = f.read_text()
        for key, value in values.items():
            text = text.replace(key, value)
        f.write_text(text)
    (dest / "results").mkdir(exist_ok=True)
    subprocess.run(["git", "init", "--quiet", "--initial-branch=main", str(dest)], check=True)
    return dest


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("site")
    ap.add_argument("dest", type=Path)
    ap.add_argument("--ad-network", required=True, choices=("Raptive", "Mediavine"))
    ap.add_argument("--name", default=None, help="site name for the report (default: the host)")
    a = ap.parse_args()
    name = a.name or (urlparse(a.site).hostname or "").removeprefix("www.")
    print("Before the first deploy, check the Worker name in deploy/cloudflare.config.ts is not already in "
          "`cf workers list`: a clash overwrites another report, which sits behind another client's Access policy.")
    dest = scaffold(a.site, a.dest.expanduser().resolve(), a.ad_network, name)
    print(f"{dest}: edit scripts/site_config.py next (pages, form fields, site vendors).")
    return 0


if __name__ == "__main__":
    sys.exit(main())

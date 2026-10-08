# /// script
# requires-python = ">=3.12"
# ///
"""Turn one audit.py run into the tables for deliverables 1, 2 and 7.

Usage:  uv run scripts/analyze.py results/<run-id>
Writes: results/<run-id>/findings.md and prints it.

"Before interaction" means a request sent in the first ~5 seconds, before the
script moved the mouse or scrolled. From a US address there is no consent
banner, so every request is made before any consent choice; the before/after
split only shows what fires the instant the page opens.
"""

import json
import re
import sys
from collections import defaultdict
from pathlib import Path
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, str(Path(__file__).parent))
from site_config import AD_NETWORK, FORM_PAGES, SITE_HOST, SITE_VENDORS  # noqa: E402

# Well-known ad-tech and data companies, for readable names. Anything not here
# and not a site vendor is listed by domain.
NAMES = {
    "mediavine.com": "Mediavine", "mediavine.net": "Mediavine", "mvcdn.net": "Mediavine",
    "adthrive.com": "Raptive (AdThrive)", "raptive.com": "Raptive", "raptivecdn.com": "Raptive",
    "ay.delivery": "Raptive header bidding (AY)", "doubleclick.net": "Google ads (DoubleClick)",
    "googlesyndication.com": "Google ads (AdSense)", "googleadservices.com": "Google ads",
    "adtrafficquality.google": "Google ads (fraud checks)", "google.com": "Google",
    "googletagservices.com": "Google ads", "gstatic.com": "Google static files",
    "scorecardresearch.com": "Comscore (Scorecard Research)", "id5-sync.com": "ID5",
    "optable.co": "Optable", "criteo.com": "Criteo", "criteo.net": "Criteo",
    "adsrvr.org": "The Trade Desk", "rlcdn.com": "LiveRamp", "liadm.com": "LiveIntent",
    "crwdcntrl.net": "Lotame", "tapad.com": "Tapad (Experian)", "adnxs.com": "Xandr (Microsoft)",
    "rubiconproject.com": "Magnite", "pubmatic.com": "PubMatic", "casalemedia.com": "Index Exchange",
    "amazon-adsystem.com": "Amazon ads", "yahoo.com": "Yahoo ads", "openx.net": "OpenX",
    "33across.com": "33Across", "sharethrough.com": "Sharethrough", "triplelift.com": "TripleLift",
    "teads.tv": "Teads", "kargo.com": "Kargo", "gumgum.com": "GumGum", "quantserve.com": "Quantcast",
    "bidswitch.net": "BidSwitch", "linkedin.com": "LinkedIn", "imrworldwide.com": "Nielsen",
    "lijit.com": "Sovrn", "sovrn.com": "Sovrn", "media.net": "Media.net", "3lift.com": "TripleLift",
    "unrulymedia.com": "Unruly", "1rx.io": "Unruly", "stackadapt.com": "StackAdapt",
    "creativecdn.com": "RTB House", "turn.com": "Amobee", "presage.io": "Ogury",
    "dotomi.com": "Epsilon (Conversant)", "bidr.io": "Beeswax", "adgrx.com": "AdGear (Samsung)",
    "admanmedia.com": "Adman", "rfihub.com": "Zeta Global", "yieldmo.com": "Yieldmo",
    "smartadserver.com": "Equativ", "onetag-sys.com": "OneTag", "rkdms.com": "Merkle",
    "cloudflare.com": "Cloudflare", "jsdelivr.net": "jsDelivr CDN", "cloudfront.net": "Amazon CloudFront",
    "adform.net": "Adform", "mathtag.com": "MediaMath", "demdex.net": "Adobe Audience Manager",
    "everesttech.net": "Adobe Advertising", "agkn.com": "Neustar", "tremorhub.com": "Tremor",
    "connatix.com": "Connatix", "jwplayer.com": "JW Player", "jwpcdn.com": "JW Player",
    "jwpltx.com": "JW Player analytics", "permutive.com": "Permutive", "permutive.app": "Permutive",
    "33across.net": "33Across", "confiant-integrations.net": "Confiant (ad security)",
    "btloader.com": "Blockthrough (ad block recovery)", "blockthrough.com": "Blockthrough",
    "brandmetrics.com": "Brandmetrics", "chocolateplatform.com": "Vidazoo/Chocolate",
    "ymmobi.com": "YieldMo mobile", "opera.com": "Opera Ads", "rtbwise.com": "RTBWise",
    "blismedia.com": "Blis", "prebid.org": "Prebid", "servenobid.com": "NoBid",
    "sitescout.com": "Basis", "ipredictive.com": "Adelphic", "contextweb.com": "PulsePoint",
    "zemanta.com": "Outbrain (Zemanta)", "outbrain.com": "Outbrain", "taboola.com": "Taboola",
}

TWO_PART_TLDS = {"co.uk", "com.au", "co.jp", "com.br"}


def reg_domain(host: str) -> str:
    parts = host.split(".")
    if ".".join(parts[-2:]) in TWO_PART_TLDS:
        return ".".join(parts[-3:])
    return ".".join(parts[-2:])


def label(dom: str, owners: dict[str, str] | None = None) -> tuple[str, str]:
    """(vendor name, who adds it). The probe inventory, when present, says who adds it."""
    if dom in SITE_VENDORS:
        name, source = SITE_VENDORS[dom]
    else:
        name, source = NAMES.get(dom, dom), f"{AD_NETWORK} ad stack (inferred)"
    if owners and dom in owners:
        source = owners[dom]
    return name, source


def inventory_owners(run: Path) -> dict[str, str]:
    """Registrable domain -> which plugin, theme or mu-plugin prints or enqueues it."""
    f = run / "inventory.json"
    if not f.exists():
        return {}
    inv = json.loads(f.read_text())
    found: dict[str, list[str]] = defaultdict(list)
    for hook, callbacks in inv.get("hooks", {}).items():
        for cb in callbacks:
            if cb.get("owner") in ("core", "internal", "unknown", None):
                continue  # core prints every enqueued script; the enqueuer is the real source
            hosts = list(cb.get("prints", {}).get("domains", []))
            hosts += [urlparse(src).hostname or "" for src in cb.get("enqueued", {}).values()]
            where = f"{cb['owner']} ({hook})"
            for host in hosts:
                if host and where not in found[reg_domain(host)]:
                    found[reg_domain(host)].append(where)
    return {d: "; ".join(w) for d, w in found.items()}


def load(run: Path):
    summary = json.loads((run / "summary.json").read_text())
    reqs = {}
    for f in run.glob("*-requests.json"):
        scenario, page = f.stem.removesuffix("-requests").split("-", 1)
        reqs[(scenario, page)] = json.loads(f.read_text())
    return summary, reqs


def main() -> None:
    run = Path(sys.argv[1])
    summary, reqs = load(run)
    owners = inventory_owners(run)
    pages = list(summary["fresh"].keys())
    out: list[str] = []
    w = out.append

    w(f"# Tracker findings - run {run.name}\n")
    bc = summary.get("bot_check", {})
    w(f"Bot check: all pages passed = {bc.get('all_pages_passed')}; "
      f"per page: {', '.join(f'{k} {v}' for k, v in bc.get('results', {}).items())}\n")

    # vendor -> page -> (total, before interaction), for the fresh run
    table = defaultdict(lambda: defaultdict(lambda: [0, 0]))
    who = {}
    for (scenario, page), rs in reqs.items():
        if scenario != "fresh":
            continue
        cut = summary["fresh"][page]["requests_before_interaction"]
        for i, r in enumerate(rs):
            host = urlparse(r["url"]).hostname or ""
            if not host or host == SITE_HOST or host.endswith("." + SITE_HOST):
                continue
            name, source = label(reg_domain(host), owners)
            who[name] = source
            cell = table[name][page]
            cell[0] += 1
            if i < cut:
                cell[1] += 1

    site_names = {v[0] for v in SITE_VENDORS.values()}
    for heading, keep in (("Installed by the site itself", lambda n: n in site_names),
                          (f"Loaded through {AD_NETWORK}'s ad code (inferred)", lambda n: n not in site_names)):
        names = sorted(n for n in table if keep(n))
        w(f"\n## {heading} - {len(names)} vendors\n")
        w("Cell = requests on that page (requests in the first ~5 s, before any mouse move or scroll). "
          "Blank = none seen.\n")
        w("| Vendor | Added by | " + " | ".join(pages) + " |")
        w("|---|---|" + "---|" * len(pages))
        for n in names:
            cells = []
            for p in pages:
                t, b = table[n].get(p, [0, 0])
                cells.append(f"{t} ({b})" if t else "")
            w(f"| {n} | {who[n]} | " + " | ".join(cells) + " |")

    # Before-interaction roll-up
    w("\n## Fired within ~5 seconds, before any interaction (fresh run)\n")
    for p in pages:
        before = sorted(n for n in table if table[n].get(p, [0, 0])[1])
        w(f"- **{p}** ({len(before)} vendors): {', '.join(before)}")

    # Cookies
    w("\n## Cookies (fresh run)\n")
    for p in pages:
        s = summary["fresh"][p]
        first = [c for c in s["cookies"] if SITE_HOST in c.split()[0]]
        third = [c for c in s["cookies"] if SITE_HOST not in c.split()[0]]
        w(f"- **{p}**: {len(s['cookies_before_interaction'])} cookies before interaction, "
          f"{len(s['cookies'])} by the end ({len(first)} first-party, {len(third)} third-party "
          f"across {len({reg_domain(c.split()[0].lstrip('.')) for c in third})} domains)")
    home = summary["fresh"]["home"]
    w("\nFirst-party cookies on the homepage by the end: "
      + ", ".join(sorted({c.split()[-1] for c in home["cookies"] if SITE_HOST in c.split()[0]})))

    # Meta, GA, consent signals
    w("\n## Meta Pixel\n")
    for (scenario, page), rs in sorted(reqs.items()):
        hits = [r for r in rs if "facebook.com/tr" in r["url"] or "facebook.com/privacy_sandbox" in r["url"]]
        if not hits:
            continue
        cut = summary[scenario][page]["requests_before_interaction"]
        evs = []
        for i, r in enumerate(rs):
            if "facebook.com/tr" in r["url"]:
                q = parse_qs(urlparse(r["url"]).query)
                q.update(parse_qs(r["post"]))
                ev = q.get("ev", ["?"])[0]
                ud = sorted(k for k in q if k.startswith("ud["))
                evs.append(f"{ev}{'*' if i < cut else ''}{' ud=' + ','.join(ud) if ud else ''}")
        w(f"- {scenario}/{page}: {', '.join(evs)}")
    w("\n(* = sent before any interaction. `ud[...]` = advanced-matching fields such as hashed email.)")

    w("\n## Google Analytics 4 events\n")
    for (scenario, page), rs in sorted(reqs.items()):
        evs = []
        for r in rs:
            if "google-analytics.com/g/collect" in r["url"] or "analytics.google.com/g/collect" in r["url"]:
                q = parse_qs(urlparse(r["url"]).query)
                body_ens = re.findall(r"(?:^|&|\n)en=([^&\n]+)", r["post"])
                evs += q.get("en", []) + body_ens
        if evs:
            w(f"- {scenario}/{page}: {', '.join(evs)}")

    w("\n## Privacy signals sent to ad partners (us_privacy / gpp strings in URLs)\n")
    for scenario in ("fresh", "gpc"):
        vals = defaultdict(int)
        for (s, page), rs in reqs.items():
            if s != scenario:
                continue
            for r in rs:
                for m in re.finditer(r"(us_privacy|usp|gpp_sid|gdpr)=([^&]{1,40})", r["url"]):
                    vals[f"{m.group(1)}={m.group(2)}"] += 1
        top = sorted(vals.items(), key=lambda kv: -kv[1])[:12]
        w(f"- {scenario}: " + ", ".join(f"`{k}` x{v}" for k, v in top))

    w("\n## Fresh vs Global Privacy Control\n")
    w("| Page | Requests fresh | Requests GPC | 3rd-party vendors fresh | GPC | Cookies fresh | GPC | Meta Pixel fresh | GPC |")
    w("|---|---|---|---|---|---|---|---|---|")
    for p in pages:
        f, g = summary["fresh"][p], summary["gpc"][p]
        mf = any("facebook.com/tr" in r["url"] for r in reqs[("fresh", p)])
        mg = any("facebook.com/tr" in r["url"] for r in reqs[("gpc", p)])
        w(f"| {p} | {f['total_requests']} | {g['total_requests']} | {len(f['vendors'])} | {len(g['vendors'])} "
          f"| {len(f['cookies'])} | {len(g['cookies'])} | {'yes' if mf else 'no'} | {'yes' if mg else 'no'} |")

    w("\n## Consent UI seen (US address)\n")
    for s in ("fresh", "gpc"):
        for p in pages:
            ui = summary[s][p]["consent_ui"]
            w(f"- {s}/{p}: links {ui['privacyLinks']}; consent elements {ui['visibleConsentElements'][:5]}; "
              f"TCF {ui['tcfApi']}, GPP {ui['gppApi']}, USP {ui['uspApi']}")

    w("\n## Form canary test (typed, never submitted)\n")
    for s in ("fresh", "gpc"):
        for p in FORM_PAGES:
            r = summary[s][p]
            w(f"- {s}/{p}: {r['form_test']}; leaks: {r['canary_leaks'] or 'none'}")

    inv_file = run / "inventory.json"
    if inv_file.exists():
        inv = json.loads(inv_file.read_text())
        w("\n## Tracker IDs stored in settings (probe inventory)\n")
        for opt, ids in sorted(inv.get("options", {}).items()):
            w(f"- `{opt}`: " + ", ".join(f"{k} {', '.join(v)}" for k, v in ids.items()))
        w("\n## Consent plugins (probe inventory)\n")
        for name, c in sorted(inv.get("consent_plugins", {}).items()):
            state = "active" if c["active"] else ("installed, inactive" if c["installed"] else "not installed")
            w(f"- {name}: {state}; option names: {', '.join(c['option_names']) or 'none'}")

    text = "\n".join(out) + "\n"
    (run / "findings.md").write_text(text)
    print(text)


if __name__ == "__main__":
    main()

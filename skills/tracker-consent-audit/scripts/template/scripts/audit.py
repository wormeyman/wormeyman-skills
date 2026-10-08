# /// script
# requires-python = ">=3.12"
# dependencies = ["playwright>=1.55"]
# ///
"""Tracker audit for the site in site_config.py.

Loads each page in a fresh browser profile (no cookies, no prior consent),
acts like a visitor (moves the mouse, scrolls - FlyingPress holds scripts back
until the visitor interacts), and records every network request and cookie.

Scenarios:
  fresh - a first visit where the visitor makes no privacy choice at all
  gpc   - the same, with Global Privacy Control turned on (Sec-GPC: 1 header
          and navigator.globalPrivacyControl = true)

On the FORM_PAGES it also types a canary email into the form WITHOUT
submitting it, and checks whether that text (or its SHA-256 hash, which is what
Meta and Google use for "advanced matching") left the browser.

It drives the installed Google Chrome (not Playwright's bundled Chromium),
headless unless you pass --visible. Bundled headless Chromium got stuck on
a host's bot check page (Pressable shows one, at /__challenge). If that
page still shows, the script ticks the "I am human" box once per browser
context and only starts recording once the real page has loaded. It exits
non-zero if any page ends on the challenge.

Run:  uv run scripts/audit.py              (writes results/ in the project folder)
      uv run scripts/audit.py --visible    (off-screen windows, if headless is challenged)
"""

import gzip
import hashlib
import json
import sys
import zlib
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from playwright.sync_api import sync_playwright

sys.path.insert(0, str(Path(__file__).parent))
from site_config import CANARY, FORM_PAGES, PAGES, SIGNUP_EMAIL, SITE, SITE_HOST  # noqa: E402

CANARY_HASH = hashlib.sha256(CANARY.encode()).hexdigest()
CHALLENGE_TEXT = "Confirm you are human"
GPC_INIT = "Object.defineProperty(Navigator.prototype, 'globalPrivacyControl', {get: () => true});"

# Hosts grouped by vendor, so the report names companies rather than domains.
VENDORS = [
    ("Meta / Facebook", ("facebook.com", "facebook.net", "fbcdn.net")),
    ("Google Analytics", ("google-analytics.com", "analytics.google.com")),
    ("Google Tag Manager / gtag", ("googletagmanager.com",)),
    ("Google ads (DoubleClick, AdSense, ad services)", (
        "doubleclick.net", "googlesyndication.com", "googleadservices.com",
        "adtrafficquality.google", "googletagservices.com",
    )),
    ("Mediavine", ("mediavine.com", "mediavine.net", "mvcdn.net")),
    ("Raptive / AdThrive", ("adthrive.com", "raptive.com", "raptivecdn.com")),
    ("Microsoft Clarity (session recording)", ("clarity.ms",)),
    ("Flodesk", ("flodesk.com", "flodesk.net")),
    ("Pinterest", ("pinterest.com", "pinimg.com")),
    ("Gauges", ("gaug.es",)),
    ("Jetpack Stats (WordPress.com)", ("stats.wp.com", "pixel.wp.com")),
    ("Kit / ConvertKit", ("convertkit.com", "kit.com", "ck.page", "kit-mail")),
    ("Stay22", ("stay22.com",)),
    ("Scorecard Research (Comscore)", ("scorecardresearch.com",)),
    ("ID5", ("id5-sync.com", "id5.io")),
    ("Optable", ("optable.co",)),
]


def body_text(req) -> str:
    """The request body as text, decompressed when it is gzip or deflate."""
    try:
        raw = req.post_data_buffer or b""
    except Exception:
        return ""
    for unpack in (gzip.decompress, zlib.decompress, lambda b: zlib.decompress(b, -15)):
        try:
            raw = unpack(raw)
            break
        except Exception:
            continue
    return raw.decode("utf-8", "replace")


def vendor_for(host: str) -> str:
    for name, suffixes in VENDORS:
        if any(host == s or host.endswith("." + s) or s in host for s in suffixes):
            return name
    return "Other: " + ".".join(host.split(".")[-2:])


def is_first_party(host: str) -> bool:
    return host == SITE_HOST or host.endswith("." + SITE_HOST)


def on_challenge(page) -> bool:
    if "/__challenge" in page.url:
        return True
    try:
        return page.get_by_text(CHALLENGE_TEXT).count() > 0
    except Exception:  # page navigating mid-check
        return False


def pass_challenge(page, requests: list) -> str:
    """Tick "I am human" if Pressable shows its bot check, then reset the log.

    Returns what happened: "not shown", "passed" or "failed".
    """
    page.wait_for_timeout(2000)  # the check sometimes passes on its own
    if not on_challenge(page):
        return "not shown"
    page.get_by_label("I am human").or_(page.locator("input[type=checkbox]")).first.check()
    try:
        page.wait_for_function(
            f"() => !document.body || !document.body.innerText.includes({CHALLENGE_TEXT!r})",
            timeout=30000,
        )
        page.wait_for_load_state("domcontentloaded")
    except Exception:
        pass
    if on_challenge(page):
        return "failed"
    # Keep only what the real page loaded: everything from the first top-level
    # document request after the last call to /__challenge. (Ad iframes are
    # documents too, so "the last document" would be wrong.)
    last_check = max((i for i, r in enumerate(requests) if "/__challenge" in r["url"]), default=-1)
    start = next((i for i, r in enumerate(requests)
                  if i > last_check and r["type"] == "document" and is_first_party(urlparse(r["url"]).hostname or "")),
                 last_check + 1)
    del requests[:start]
    return "passed"


def act_like_a_visitor(page) -> None:
    page.mouse.move(200, 300)
    page.mouse.move(400, 500)
    for _ in range(6):
        page.mouse.wheel(0, 900)
        page.wait_for_timeout(700)
    page.wait_for_timeout(8000)


def consent_ui(page) -> dict:
    """Look for a consent banner and privacy links the visitor can see."""
    return page.evaluate(
        """() => {
        const visible = el => { const r = el.getBoundingClientRect();
          const s = getComputedStyle(el);
          return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none'; };
        const links = [...document.querySelectorAll('a, button')]
          .filter(visible)
          .map(el => (el.innerText || '').trim().replace(/\\s+/g, ' '))
          .filter(t => /privacy|do not sell|opt.?out|cookie|consent|terms|disclos/i.test(t));
        const banners = [...document.querySelectorAll('[id*=cmp i], [class*=cmp i], [id*=consent i], [class*=consent i], [id*=cookie i], [class*=cookie i]')]
          .filter(visible)
          .map(el => (el.id || el.className || '').toString().slice(0, 80));
        return {
          privacyLinks: [...new Set(links)],
          visibleConsentElements: [...new Set(banners)].slice(0, 20),
          tcfApi: typeof window.__tcfapi === 'function',
          gppApi: typeof window.__gpp === 'function',
          uspApi: typeof window.__uspapi === 'function',
        };
    }"""
    )


def type_canary(page) -> str:
    fields = page.locator(SIGNUP_EMAIL)
    field = next((fields.nth(i) for i in range(fields.count()) if fields.nth(i).is_visible()), None)
    if field is None:
        return f"no visible sign-up email field ({fields.count()} hidden)"
    field.scroll_into_view_if_needed()
    field.click()
    field.press_sequentially(CANARY, delay=60)
    page.mouse.move(10, 10)  # blur-ish movement, still no submit
    page.wait_for_timeout(6000)
    return "typed canary, did not submit"


def run(scenario: str, out: Path, pw) -> dict:
    # Real Chrome, headless by default so no windows pop up. --visible opens
    # one window per page, parked off-screen so it stays out of the way.
    visible = "--visible" in sys.argv
    browser = pw.chromium.launch(
        channel="chrome", headless=not visible,
        args=["--window-position=-2400,-2400"] if visible else [],
    )
    results = {}
    for name, path in PAGES.items():
        extra = {"Sec-GPC": "1"} if scenario == "gpc" else {}
        ctx = browser.new_context(
            viewport={"width": 1366, "height": 900},
            extra_http_headers=extra, locale="en-US", timezone_id="America/Denver",
        )
        if scenario == "gpc":
            ctx.add_init_script(GPC_INIT)
        requests = []
        ctx.on("request", lambda r: requests.append({
            "url": r.url, "method": r.method, "type": r.resource_type,
            "post": body_text(r)[:20000] if r.method == "POST" else "",
        }))
        page = ctx.new_page()
        page.goto(SITE + path, wait_until="domcontentloaded", timeout=60000)
        challenge = pass_challenge(page, requests)
        page.wait_for_timeout(3000)
        before_interaction = len(requests)
        cookies_before = ctx.cookies()
        page.screenshot(path=out / f"{scenario}-{name}-top.png")
        act_like_a_visitor(page)
        form_note = type_canary(page) if name in FORM_PAGES else ""
        ui = consent_ui(page)
        page.screenshot(path=out / f"{scenario}-{name}-end.png", full_page=False)
        cookies = ctx.cookies()

        leaks = [r["url"][:200] for r in requests
                 if CANARY in r["url"] or CANARY_HASH in r["url"]
                 or CANARY in r["post"] or CANARY_HASH in r["post"]
                 or CANARY.replace("@", "%40") in r["url"] + r["post"]]
        third = {}
        for i, r in enumerate(requests):
            host = urlparse(r["url"]).hostname or ""
            if not host or is_first_party(host) or r["url"].startswith("data:"):
                continue
            v = third.setdefault(vendor_for(host), {"hosts": set(), "requests": 0, "before_interaction": 0})
            v["hosts"].add(host)
            v["requests"] += 1
            if i < before_interaction:
                v["before_interaction"] += 1
        meta_events = sorted({
            (r["url"] + "&" + r["post"]).split("ev=")[1].split("&")[0]
            for r in requests if "facebook.com/tr" in r["url"] and "ev=" in r["url"] + r["post"]
        })
        stuck = on_challenge(page)
        results[name] = {
            "url": SITE + path,
            "final_url": page.url,
            "challenge": challenge,
            "ended_on_challenge": stuck,
            "total_requests": len(requests),
            "requests_before_interaction": before_interaction,
            "vendors": {k: {**v, "hosts": sorted(v["hosts"])} for k, v in sorted(third.items())},
            "meta_pixel_events": meta_events,
            "cookies_before_interaction": sorted({f'{c["domain"]}  {c["name"]}' for c in cookies_before}),
            "cookies": sorted({f'{c["domain"]}  {c["name"]}' for c in cookies}),
            "consent_ui": ui,
            "form_test": form_note,
            "canary_leaks": leaks,
        }
        (out / f"{scenario}-{name}-requests.json").write_text(json.dumps(requests, indent=1))
        ctx.close()
        print(f"  {scenario}/{name}: challenge {challenge}, {len(requests)} requests, "
              f"{len(third)} vendors{'  STILL ON CHALLENGE' if stuck else ''}", file=sys.stderr)
    browser.close()
    return results


def main() -> None:
    out = Path(__file__).resolve().parent.parent / "results" / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out.mkdir(parents=True)
    with sync_playwright() as pw:
        summary = {s: run(s, out, pw) for s in ("fresh", "gpc")}
    stuck = [f"{s}/{n}" for s, pages in summary.items() for n, r in pages.items()
             if r["ended_on_challenge"] or r["challenge"] == "failed"]
    summary["bot_check"] = {
        "all_pages_passed": not stuck,
        "stuck_pages": stuck,
        "results": {f"{s}/{n}": r["challenge"] for s in ("fresh", "gpc") for n, r in summary[s].items()},
    }
    (out / "summary.json").write_text(json.dumps(summary, indent=1))
    print(out)
    if stuck:
        sys.exit(f"FAILED: still on Pressable's bot check at {', '.join(stuck)} - results are not usable")


if __name__ == "__main__":
    main()

# /// script
# requires-python = ">=3.12"
# dependencies = ["playwright>=1.55"]
# ///
"""Form canary test on a normal post, where every tracker on the site runs.

This opens a post, finds the first visible field in FORM_TEST_FIELDS, types a canary address one key at a time WITHOUT submitting, and
checks every request sent afterwards for the address, its URL-encoded form,
or its SHA-256 / MD5 hash. Request bodies are searched after gzip or deflate
decompression too, since session recorders such as Microsoft Clarity compress
their uploads. Headless real Chrome, so no windows open.

Run:  uv run scripts/form_test.py results/<run-id>
"""

import hashlib
import json
import sys
from pathlib import Path
from urllib.parse import quote, urlparse

from playwright.sync_api import sync_playwright

sys.path.insert(0, str(Path(__file__).parent))
from audit import body_text  # noqa: E402
from site_config import CANARY, FORM_TEST_FIELDS, PAGES, RECORDER_UPLOADS, SITE  # noqa: E402

URL = SITE + PAGES["post"]
NEEDLES = {
    "plain": CANARY,
    "url-encoded": quote(CANARY, safe=""),
    "sha256": hashlib.sha256(CANARY.encode()).hexdigest(),
    "md5": hashlib.md5(CANARY.encode()).hexdigest(),
    "local part": CANARY.split("@")[0],
}


def main() -> None:
    out = Path(sys.argv[1])
    requests = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel="chrome", headless="--visible" not in sys.argv)
        ctx = browser.new_context(viewport={"width": 1366, "height": 900}, locale="en-US",
                                  timezone_id="America/Denver")
        ctx.on("request", lambda r: requests.append({
            "url": r.url, "method": r.method, "type": r.resource_type,
            "post": body_text(r) if r.method == "POST" else "",
        }))
        page = ctx.new_page()
        page.goto(URL, wait_until="domcontentloaded", timeout=60000)
        page.mouse.move(200, 300)
        page.wait_for_timeout(4000)
        fields = page.locator(FORM_TEST_FIELDS[0])

        def visible_field():
            return next((fields.nth(i) for i in range(fields.count()) if fields.nth(i).is_visible()), None)

        field = visible_field()
        if field is None:
            # Inline forms sit further down; pop-ups open on scroll or exit intent.
            for _ in range(12):
                page.mouse.wheel(0, 900)
                page.wait_for_timeout(500)
                if (field := visible_field()) is not None:
                    break
        if field is None:
            page.mouse.move(600, 200)
            page.mouse.move(600, 0)  # exit intent: cursor leaves through the top
            page.wait_for_timeout(3000)
            field = visible_field()
        if field is None:
            print(f"form test fields in DOM: {fields.count()}, none visible", file=sys.stderr)
            sys.exit("no visible form test field found")
        form_html = field.evaluate("el => (el.closest('form') || el.parentElement).outerHTML.slice(0, 400)")
        field.scroll_into_view_if_needed()
        page.wait_for_timeout(3000)
        start = len(requests)
        field.click()
        field.press_sequentially(CANARY, delay=80)
        page.keyboard.press("Tab")  # blur the field, still no submit
        for selector in FORM_TEST_FIELDS[1:]:
            extra = page.locator(selector).first
            if extra.count():
                extra.click()
                extra.press_sequentially(CANARY, delay=80)
                page.keyboard.press("Tab")
        page.mouse.move(600, 400)
        typed = len(requests)

        def recorder_uploads() -> list:
            return [r for r in requests[typed:] if any(u in r["url"] for u in RECORDER_UPLOADS) and r["method"] == "POST"]

        # "No canary found" only means something if the recorder uploaded after
        # the typing. Wait up to 60 s for an upload, then leave the page, which
        # makes the recorder flush what it has buffered.
        for _ in range(60):
            if recorder_uploads():
                break
            page.wait_for_timeout(1000)
        page.wait_for_timeout(5000)
        page.screenshot(path=out / "form-test-post.png")
        flushed_on_leave = not recorder_uploads()
        page.goto(SITE + "/", wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(5000)
        browser.close()

    after = requests[start:]
    hits = []
    for r in after:
        blob = r["url"] + "\n" + r["post"]
        found = [k for k, v in NEEDLES.items() if v in blob]
        if found:
            hits.append({"url": r["url"][:200], "method": r["method"], "matched": found})
    hosts = sorted({urlparse(r["url"]).hostname or "" for r in after})
    result = {
        "page": URL,
        "form_found": form_html,
        "requests_after_typing": len(after),
        "hosts_contacted_after_typing": hosts,
        "canary_hits": hits,
        "recorder_uploads_after_typing": len(recorder_uploads()),
        "recorder_upload_bytes_after_typing": sum(len(r["post"]) for r in recorder_uploads()),
        "recorder_flushed_only_on_leaving_page": flushed_on_leave,
    }
    if not recorder_uploads():
        result["warning"] = "the session recorder sent nothing after the typing, so no canary hits proves nothing"
    (out / "form-test.json").write_text(json.dumps(result, indent=1))
    print(json.dumps(result, indent=1))


if __name__ == "__main__":
    main()

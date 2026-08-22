---
name: accessibility-audit
description: Audit a web page, local file, or published artifact against WCAG 2.2 AA, then fix what it finds. Use whenever the user asks whether something is accessible, says "a11y", "WCAG", "ADA", "Section 508", "screen reader", "color contrast", "keyboard navigation", "tab order", or asks to run Lighthouse for accessibility - and also proactively right after building or restyling any page, because contrast and keyboard defects ship silently. Covers the theme matrix (one Lighthouse run only tests whichever theme the browser happens to be in), computed contrast sweeps, the checks Lighthouse does not run, and auditing published artifacts, which cannot be audited at their claude.ai URL.
---

# Accessibility Audit

Audit a page, report findings with severity, fix on approval, then re-run to prove the score moved.

## Relationship to `a11y-debugging`

The chrome-devtools plugin ships an `a11y-debugging` skill. It is good and this does not replace it. Split the work:

| Use `a11y-debugging` for | Use this skill for |
|---|---|
| Reading the accessibility tree | The theme matrix |
| Form labels, orphaned inputs | Computed contrast sweeps |
| ARIA attributes and roles | Checks Lighthouse omits entirely |
| Focus traps in modals | Auditing published artifacts |
| Per-element tap-target checks | The fix-and-verify loop |

If a page has forms, modals, or heavy ARIA, run that skill too. Do not re-derive its material here.

## The one rule that matters most

**Lighthouse only ever audits the theme the browser is currently rendering.** It does not test both. A theme-aware page audited once has been half audited, and the half you skipped is usually the worse one.

Two measured examples, both reproducible:

A real page scored **87 in dark mode with zero contrast findings**. Forced to light, the same page scored **77 with 41 failing elements**. The single run was not a smaller version of the truth. It was the wrong answer.

Worse, the score does not have to move at all. `references/fixture.html` scores **62 in both themes** - and the contrast failures behind that identical number do not overlap at all:

| | Elements Lighthouse flags |
|---|---|
| Dark | `p.dark-fail`, `span.status.good` |
| Light | `p.light-fail`, and four `<th>` |

Fix everything the dark run reports and the page still has five contrast failures in light, still scoring 62. **A stable score across themes is not evidence the themes are equally sound.** Always run the matrix in Step 2.

---

## Step 1 - Get an auditable URL

Three cases. Pick the right one before running anything.

**A live site.** Audit the URL directly. Nothing to set up.

**A local file.** Serve it over HTTP. Never audit `file://` - Lighthouse behaves differently and some audits silently skip.

```bash
cd <dir> && python3 -m http.server 8731 --bind 127.0.0.1
```

Run it with `run_in_background: true`, and kill it when finished.

**A published artifact.** This is the case people get wrong. Pointing Lighthouse at `https://claude.ai/code/artifact/<uuid>` audits the claude.ai wrapper page, not your content. The score is meaningless.

Instead, wrap your source file in the same skeleton the publisher applies and serve that locally:

```html
<!doctype html>
<html>
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<style>*{margin:0;padding:0}</style></head>
<body>
<!-- your artifact source file, verbatim -->
</body></html>
```

Build a second copy with `<html lang="en">`. You author body content, not the `<html>` tag, so `html-has-lang` is the publisher's to fix and it costs 7 points. Auditing both copies separates your score from theirs - report the with-lang number as your content's true score and name the gap.

## Step 2 - Run the theme matrix

Never a single run. Minimum three:

| Run | Setup |
|---|---|
| Desktop light | `emulate` with `colorScheme: "light"`, then `lighthouse_audit` |
| Desktop dark | `emulate` with `colorScheme: "dark"`, then `lighthouse_audit` |
| Mobile | `lighthouse_audit` with `device: "mobile"` - reflow and tap-target rules only run here |

`emulate` persists across navigations, so set it once per theme and run everything for that theme before switching.

Gotchas that cost real time:

- **A run reporting 0 across every category, with 0 passed *and* 0 failed, is a failed run, not a score.** Nothing was measured. Check `runtimeError` in the JSON and retry before you conclude anything. Live sites behind a WAF or CDN throw this: a real audit of a production WordPress site returned `ERRORED_DOCUMENT_REQUEST` with a 403 on the first attempt and scored 96 on an immediate retry, with no change to anything. The distinction matters because a genuine 0 and a failed run look identical in the summary, and only one of them is worth reporting.
- `lighthouse_audit` rejects `outputDirPath` outside the configured workspace roots. Omit it and take the temp path from the result, then copy the HTML report somewhere durable if you want to keep it.
- The result summary's "Failed: N" counts every category, not just accessibility. Read the JSON for the real accessibility failures.
- Never read `report.json` raw. It runs to hundreds of KB. Extract with the script in `references/scripts.md`.

## Step 3 - Sweep contrast by computation

Lighthouse samples. It also cannot see a failure in the theme it did not render. Compute contrast yourself against what the browser actually painted.

Run the **contrast sweep** from `references/scripts.md` via `evaluate_script`, once per theme. It walks every text-bearing element, resolves the real effective background by climbing ancestors until it finds a non-transparent one, and applies the correct threshold for that element's computed size and weight (3:1 for large text, 4.5:1 otherwise).

Trust it over Lighthouse's contrast audit. It reports exact ratios, which is what you need to pick a replacement color.

**If you are also authoring the page, check the palette before building.** Contrast is far cheaper to fix in six token values than in 41 rendered elements. Run the **token pre-check** from `references/scripts.md` against your palette, in both themes, before writing components. Test each foreground against the *darkest* light surface and the *lightest* dark surface - those are the worst cases, and a token that clears white may still fail on a tinted panel.

## Step 4 - Run what Lighthouse does not

These are real WCAG failures with no Lighthouse audit behind them. Run the **structural check** from `references/scripts.md`, then verify by hand:

- **Keyboard access to scrollable regions.** Any `overflow-x: auto` container holding a wide table or code block is unreachable by keyboard without `tabindex="0"`. Lighthouse does not run axe's `scrollable-region-focusable` rule at all.
- **Table header semantics.** `th` without `scope`, and first-column cells marked up as `td` when they are functionally row headers. Lighthouse's table audits return "not applicable" and tell you nothing.
- **Color as the only signal.** Status shown by red text alone, a colored rail with no text label, a chart series distinguished only by hue. Run the **polarity probe** from `references/scripts.md`, then read what it surfaces.
  The trap is not the empty cell, it is the **full** one. `+$1,000` and `+$130` are both complete, specific, correctly formatted values, and on a real page the first was good news and the second was bad, distinguishable only by being green or red. Asking "what does a colorblind user lose here" answers "nothing, the numbers are right there" and you move on. **Ask instead whether the text alone reveals which direction is better.** A signed number, a bare percentage, a date, a name: none of them carry polarity.
- **Two colors encoding opposite states.** Run the **status-pair luminance check** from `references/scripts.md`. Contrast tools compare each color to its background; both can pass and still be the same brightness as each other, leaving hue as the only difference. Greyscale and color vision deficiency both erase hue.
- **Focus visibility.** Tab through interactively. Anything focusable needs a visible `:focus-visible` state, including containers you just gave `tabindex="0"`.
- **Reflow.** At 320px wide, the page body must not scroll sideways. Wide content scrolls inside its own container.

## Step 5 - Report

Group by severity, and state clearly which findings are yours to fix versus the host's. A score with an unexplained cap is not useful information.

Report per theme. "95 in both themes" and "95 light, 77 dark" are very different results.

**If the page ships no `prefers-color-scheme` rules at all, say the matrix was confirmatory.** Plenty of sites have one theme. Reporting three identical runs as though they were three independent findings overstates the work and buries the real ones. Say the site has a single theme, that you verified it rather than assumed it, and move on. The structural check reports `prefersDarkSupported` for exactly this call - but treat a `false` there as a prompt to confirm by running the other theme, never as permission to skip it.

**Watch the denominator on mobile.** Mobile runs fewer audits than desktop, so a one-point gap between them is usually arithmetic rather than a defect. Compare the failure lists, not the scores, before reporting a difference.

## Step 6 - Fix, then verify

Apply fixes, then **re-run the full matrix**. A fix verified in one theme is not verified.

State the before and after numbers per theme. If a number did not move, say so rather than implying it did.

## Red flags

| Thought | Reality |
|---|---|
| "Lighthouse says 95, we're good" | In which theme? Run the matrix. |
| "The contrast audit passed" | It only checked the rendered theme, and it samples. Sweep it. |
| "I'll audit the artifact URL" | That audits claude.ai's wrapper. Serve it locally. |
| "No tables or forms, so semantics are fine" | Scroll containers and heading order still fail silently. |
| "It's a static page, keyboard access is moot" | Scrollable regions are interactive whether you intended it or not. |
| "I'll read the Lighthouse JSON to find failures" | It is hundreds of KB. Use the extractor. |
| "Score went 77 to 95, done" | Re-run every theme. And name what caps the remaining 5. |
| "It scored 0, the page must be broken" | 0 with nothing passed and nothing failed means the run failed. Check `runtimeError` and retry. |
| "Desktop 96, mobile 95, so mobile is worse" | Mobile runs fewer audits. Compare failure lists, not scores. |

## Verifying this skill still works

`references/fixture.html` has ten planted defects and a manifest in its source comment. Serve it and run the full workflow against it.

Expected result. Eight are caught by script:

| Found in | Defect |
|---|---|
| Light run only | `.light-fail` contrast, 2.75:1 |
| Dark run only | `.dark-fail` contrast, 2.03:1 |
| Both runs | no `<main>`, no `lang`, `H1 H3` heading skip, missing `alt` |
| Both runs | scroll region with no tab stop and no label |
| Both runs | table with no caption and four `th` with no scope |
| Focus probe | link with `outline:none` and no replacement |

The tenth - state carried by color alone in the status column - has no *definitive* check. The polarity probe surfaces it as a candidate (`span.status.good`, text "caught", which does not reveal whether being caught is good or bad), alongside two false positives from `.light-fail` and `.dark-fail`, whose class names describe the planted defect rather than a UI state. **Three candidates, one real.** That ratio is the point: the probe generates leads, you decide. If a run reports the fixture clean on defect 10 without looking at the candidates, that is the failure the manual pass in Step 4 exists to prevent.

If a script-detectable defect is missed, the skill has regressed. Fix the skill, not the fixture.

## References

- `references/scripts.md` - contrast sweep, token pre-check, structural check, Lighthouse JSON extractor
- `references/fixes.md` - finding-to-fix patterns
- `references/fixture.html` - page with planted defects, for verifying this skill still works

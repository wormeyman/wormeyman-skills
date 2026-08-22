# Finding-to-fix patterns

Each entry: what you saw, why it fails, what to change. Use these instead of re-deriving the fix every audit.

---

## Contrast below threshold

**Fix in tokens, not in components.** A ratio of 4.06:1 on a muted grey usually means one variable is used in fifteen places. Change the variable.

Pick the new value against the **worst** surface that foreground lands on, not against white. Give yourself margin - a value that computes to exactly 4.50 will fail again the moment someone tints a panel.

```css
/* before: --ink-3:#6E7A82 -> 4.06:1 on #F4F6F7, fails */
/* after                                              */
--ink-3:#5A666E;  /* 5.44:1 on ground, 4.85:1 worst case */
```

Watch for the same token in the dark theme. Light and dark need separate values and separate verification.

## Text set in a border or rule color

Decorative separators (`/`, `·`, `|`) written as real text nodes get audited as text and will fail, because rule colors are chosen to be faint.

Move them into CSS so they stop being text:

```css
.eyebrow span + span::before { content:"/"; color:var(--rule); margin-right:9px; }
```

Generated content is not flagged by contrast rules. If the separator is genuinely meaningful rather than decorative, it is not a separator - give it a real color.

## Scrollable region unreachable by keyboard

Any `overflow-x:auto` container that actually overflows is interactive, whether you intended it or not. A keyboard user cannot reach it without a tab stop.

Lighthouse does not run this rule. You have to check it yourself.

```html
<div class="scroll" tabindex="0" role="region" aria-label="Comparison of paper against registry records">
  <table>...</table>
</div>
```

```css
.scroll:focus-visible { outline:2px solid var(--accent-2); outline-offset:3px; }
```

The `aria-label` is required, not optional - an unlabeled region announces as "region" and tells the user nothing. Label it with what the table shows.

## Table header semantics

Lighthouse's table audits return "not applicable" here and tell you nothing. Two fixes, usually together:

```html
<thead><tr><th scope="col">Item</th><th scope="col">Value</th></tr></thead>
<tbody><tr><th scope="row">study type</th><td>Observational</td></tr></tbody>
```

The first cell of each body row is nearly always a row header. If it labels the row rather than carrying data, it is a `th`, and `td` is wrong.

Restyle `tbody th` explicitly - browsers default it to bold and centered, which is rarely what the design wants.

```css
tbody th { font-weight:500; text-align:left; }
```

## Color as the only signal

Red text marking a bad value, a colored rail with no label, a series distinguished only by hue. The polarity probe in `scripts.md` generates candidates; you decide which are real.

Add a redundant text cue:

```html
<td><span class="flagtag">differs</span>Observational: watch and record only</td>
```

A color-coded card is fine **if** it also carries a text chip saying "Not supported". The color then reinforces rather than carries.

### The hard case: complete text, absent polarity

The dangerous version is not a missing label, it is a value that looks finished.
In a year-over-year plan table, `+$500` was a larger annual allowance (good) and
`+$25` was a higher monthly fee (bad). Both cells were specific and correctly
formatted, both were dollars, both carried a plus sign. Only red versus green
said which way was up.

Sign does not equal direction. Whether "more" is good depends on the row.

```html
<!-- before: polarity lives in the class, and therefore in the color -->
<td class="worse">+$25</td>
<td class="better">+$500</td>

<!-- after: polarity lives in the text; color now reinforces -->
<td class="worse">+$25 <span class="dir">worse</span></td>
<td class="better">+$500 <span class="dir">better</span></td>
```

```css
.dir {
  font-size: .58rem;
  letter-spacing: .09em;
  text-transform: uppercase;
  white-space: nowrap;
  /* inherit the cell color: no new token, no new contrast pair to verify */
}
```

Do not reach for `aria-label` or visually hidden text here. A screen reader
would get the direction, but a **sighted** colorblind reader gets nothing, and
they are the population this criterion is about. The cue has to be visible.

On a dense table this adds a word to every changed cell. That is the cost, and
it is the right trade: a reference table people make decisions from should not
require distinguishing red from green under a deadline.

## No main landmark

`landmark-one-main`. Screen reader users navigate by landmark and skip-to-content depends on it.

Wrap the page content in `<main>`. Exactly one per document. If you already have a wrapper div doing layout, make that the `<main>` rather than nesting another element.

## Missing `lang` on `<html>`

Costs 7 points and changes which voice a screen reader uses.

**On a published artifact you cannot fix this** - you author body content, not the `<html>` tag. Audit a second local copy with `<html lang="en">` to separate your score from the wrapper's, and report both numbers.

Everywhere else, just set it.

## Heading level skipped

`H1 H2 H4` breaks navigation for anyone moving by heading. Fix the markup, not the appearance - if H3 looks wrong there, style it, do not relabel it.

## Body scrolls sideways

Fails reflow at 320px. The page body must never scroll horizontally; wide content scrolls inside its own container.

```css
.scroll { overflow-x:auto; }
table    { min-width:640px; }   /* the table scrolls, the page does not */
```

Check at a 320px viewport, not just at desktop width.

## Type too small to read

Not a WCAG failure on its own, so nothing flags it. Labels at 10.5px in uppercase with letter-spacing are still hard to read for anyone with low vision.

Set uppercase mono labels no smaller than 11.5px. It costs nothing.

## Focus not visible

Every focusable element needs a visible state, including containers you just gave `tabindex="0"`.

```css
a:focus-visible, .scroll:focus-visible {
  outline:2px solid var(--accent-2); outline-offset:3px; border-radius:3px;
}
```

Never `outline:none` without a replacement. Use `:focus-visible` rather than `:focus` so mouse users do not see rings they did not ask for.

## Animation with no reduced-motion guard

If the page animates, guard it. If it does not animate, there is nothing to add - say so rather than claiming credit for a media query that guards nothing.

```css
@media (prefers-reduced-motion:reduce) {
  *,*::before,*::after { animation-duration:.01ms !important; transition-duration:.01ms !important; }
}
```

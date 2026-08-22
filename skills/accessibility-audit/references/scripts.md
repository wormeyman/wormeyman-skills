# Scripts

Six scripts. All but one run in the page via `evaluate_script`; the Lighthouse extractor runs in bash against a saved report.

All of these were written against a real audit and returned correct results on a page where Lighthouse's own contrast audit reported a false pass.

---

## 1. Contrast sweep

Run once per theme. Walks every text-bearing element, resolves the real effective background by climbing ancestors until it finds a non-transparent one, and applies the correct WCAG threshold for that element's computed size and weight.

Use this instead of trusting Lighthouse's contrast audit. It reports exact ratios, which is what you need in order to pick a replacement color.

```js
() => {
  const srgb = c => { c/=255; return c<=0.04045 ? c/12.92 : Math.pow((c+0.055)/1.055,2.4); };
  const lum = ([r,g,b]) => 0.2126*srgb(r)+0.7152*srgb(g)+0.0722*srgb(b);
  const parse = s => (s.match(/[\d.]+/g)||[]).map(Number);
  const cr = (a,b) => { const la=lum(a),lb=lum(b),hi=Math.max(la,lb),lo=Math.min(la,lb); return (hi+0.05)/(lo+0.05); };
  const bgOf = el => { let n=el;
    while (n && n!==document.documentElement) {
      const c=parse(getComputedStyle(n).backgroundColor);
      if (c.length>=3 && (c.length===3 || c[3]>0)) return c.slice(0,3);
      n=n.parentElement; }
    return [255,255,255]; };
  const out=[];
  document.querySelectorAll('*').forEach(el=>{
    const hasText=[...el.childNodes].some(n=>n.nodeType===3&&n.textContent.trim().length);
    if(!hasText) return;
    const cs=getComputedStyle(el);
    if(cs.visibility==='hidden'||cs.display==='none') return;
    const px=parseFloat(cs.fontSize), w=parseInt(cs.fontWeight)||400;
    const need=(px>=24||(px>=18.66&&w>=700))?3:4.5;
    const ratio=cr(parse(cs.color).slice(0,3), bgOf(el));
    if(ratio<need) out.push({
      sel: el.tagName.toLowerCase()+(typeof el.className==='string'&&el.className?'.'+el.className.trim().split(/\s+/).join('.'):''),
      text: el.textContent.trim().slice(0,40),
      px, weight:w, ratio:+ratio.toFixed(2), need
    });
  });
  const agg={};
  out.forEach(o=>{ const k=o.sel+'@'+o.px; agg[k]=agg[k]||{...o,count:0}; agg[k].count++; });
  return {
    scheme: matchMedia('(prefers-color-scheme: dark)').matches?'dark':'light',
    bodyBg: getComputedStyle(document.body).backgroundColor,
    totalFailingElements: out.length,
    failures: Object.values(agg)
  };
}
```

`scheme` and `bodyBg` are in the output on purpose. Check them. If `scheme` is not the theme you meant to test, your `emulate` call did not take effect and the run is worthless. A `bodyBg` of `rgba(0, 0, 0, 0)` means the page never painted its own background and is borrowing the host's - a bug in its own right.

---

## 2. Token pre-check

Run in bash **before building**, against the palette you plan to use. Contrast is far cheaper to fix in six token values than in dozens of rendered elements.

Test each foreground against the **darkest light surface** and the **lightest dark surface**. Those are the worst cases. A token that clears white can still fail on a tinted panel, which is exactly how most of these ship.

```python
def srgb(c):
    c=c/255
    return c/12.92 if c<=0.04045 else ((c+0.055)/1.055)**2.4
def lum(h):
    h=h.lstrip('#'); r,g,b=(int(h[i:i+2],16) for i in (0,2,4))
    return 0.2126*srgb(r)+0.7152*srgb(g)+0.0722*srgb(b)
def cr(a,b):
    la,lb=lum(a),lum(b); hi,lo=max(la,lb),min(la,lb)
    return (hi+0.05)/(lo+0.05)

# every surface a foreground can land on, per theme
SURFACES = ["#F4F6F7","#FFFFFF","#EAEEEF","#E0EBED"]

for fg in ["#6E7A82","#5F6B73","#5A666E","#556169"]:
    ratios = [cr(fg,bg) for bg in SURFACES]
    worst  = min(ratios)
    print(f"{fg}  worst {worst:.2f}  {'OK' if worst>=4.5 else 'FAILS'}  " +
          "  ".join(f"{bg}:{r:.2f}" for bg,r in zip(SURFACES,ratios)))
```

Thresholds: **4.5:1** normal text, **3:1** for text at or above 24px, or at or above 18.66px when bold. Non-text UI (borders, icons, focus rings) needs **3:1**.

---

## 3. Structural check

Run once per theme. Covers the things Lighthouse either does not test or reports as "not applicable", which reads as a pass and is not one.

```js
() => {
  const scrolls=[...document.querySelectorAll('*')].filter(el=>{
    const o=getComputedStyle(el).overflowX;
    return (o==='auto'||o==='scroll') && el.scrollWidth>el.clientWidth;
  });
  return {
    scheme: matchMedia('(prefers-color-scheme: dark)').matches?'dark':'light',
    prefersDarkSupported: [...document.styleSheets].some(s=>{
      try { return [...s.cssRules].some(r=>r.conditionText && r.conditionText.includes('prefers-color-scheme')); }
      catch(e) { return false; }   // cross-origin sheet, cannot read
    }),
    mainLandmarks: document.querySelectorAll('main').length,
    htmlLang: document.documentElement.lang || '(none)',
    headingOrder: [...document.querySelectorAll('h1,h2,h3,h4,h5,h6')].map(h=>h.tagName).join(' '),
    scrollRegions: scrolls.length,
    scrollRegionsKeyboardReachable: scrolls.every(s=>s.tabIndex>=0),
    scrollRegionsLabeled: scrolls.every(s=>s.getAttribute('aria-label')||s.getAttribute('aria-labelledby')),
    tablesMissingCaption: [...document.querySelectorAll('table')].filter(t=>!t.querySelector('caption')).length,
    thMissingScope: document.querySelectorAll('th:not([scope])').length,
    imagesMissingAlt: document.querySelectorAll('img:not([alt])').length,
    bodyScrollsSideways: document.documentElement.scrollWidth > document.documentElement.clientWidth,
    focusableWithNoVisibleFocus: (() => {
      const bad=[...document.querySelectorAll('a[href],button,input,select,textarea,[tabindex]:not([tabindex="-1"])')]
        .filter(el=>{
          el.focus();
          const cs=getComputedStyle(el);
          const noOutline = cs.outlineStyle==='none' || parseFloat(cs.outlineWidth)===0;
          return noOutline && cs.boxShadow==='none';
        })
        .map(el=>el.tagName.toLowerCase()+':'+el.textContent.trim().slice(0,24));
      if (document.activeElement) document.activeElement.blur();
      return bad;
    })()
  };
}
```

Reading the output:

- `mainLandmarks` of 0 fails `landmark-one-main`. More than 1 is also wrong.
- `headingOrder` should never skip a level. `H1 H2 H4` is a failure.
- `scrollRegionsKeyboardReachable: false` means keyboard users cannot scroll your wide tables. Lighthouse does not test this.
- `thMissingScope` above 0 is a fix even though Lighthouse says nothing.
- `bodyScrollsSideways: true` fails reflow. Check it again at a 320px viewport.
- `prefersDarkSupported: false` means the page ships no dark-theme rules, so the two theme runs will agree. Report the matrix as confirmatory rather than as two findings. Treat it as a prompt to confirm, never as permission to skip the second run: cross-origin stylesheets throw on `cssRules` and are counted as `false`, so a themed page served from a CDN can report `false` and still have a dark theme.
- `focusableWithNoVisibleFocus` lists anything that takes focus and shows nothing. The probe focuses each candidate, reads its computed style, and restores focus afterwards. It catches `outline:none` with no replacement, which is the single most common focus bug.

---

## 4. Lighthouse JSON extractor

The report runs to hundreds of KB. Never read it raw into context.

```python
import json, glob, os
f = sorted(glob.glob("/var/folders/*/*/T/chrome-devtools-mcp-*/report.json"),
           key=os.path.getmtime)[-1]          # newest report
r = json.load(open(f))
c = r["categories"]["accessibility"]
print("SCORE:", round(c["score"]*100), "|", f)

print("\nFAILURES:")
for ref in c["auditRefs"]:
    a = r["audits"][ref["id"]]
    if a.get("score") is not None and a["score"] < 1:
        print(f"\n### {a['id']} (weight {ref.get('weight')}) - {a.get('title')}")
        for it in (a.get("details") or {}).get("items", [])[:12]:
            n = it.get("node", {})
            print("   -", (n.get("snippet") or "")[:120])
            if n.get("explanation"):
                print("     >>", n["explanation"][:200])

na = [ref["id"] for ref in c["auditRefs"]
      if r["audits"][ref["id"]].get("scoreDisplayMode") == "notApplicable"]
print("\nNOT APPLICABLE (nothing on the page to test - not a pass):")
print(", ".join(na))
```

The glob path is macOS. On Linux the reports land under `/tmp`.

Read the "not applicable" list. It is the honest answer to "what did this audit not check", and it is where the false confidence lives.


---

## 5. Polarity probe

Run once per page. Finds elements whose **class** encodes a good/bad direction
while their **visible text** does not, which means colour is the only thing
carrying polarity. WCAG 1.4.1.

This is a lead generator, not a verdict. Read every candidate.

```js
() => {
  const POLARITY_CLASS = /(worse|better|bad|good|up|down|pos|neg|pass|fail|error|success|warn|danger|alert|critical|ok|high|low|gain|loss|increase|decrease)/i;
  const POLARITY_TEXT  = /\b(worse|better|worsened|improved|up|down|higher|lower|increase[ds]?|decrease[ds]?|gain(ed)?|lost|loss|rose|fell|good|bad|pass(ed|ing)?|fail(ed|ing|ure)?|error|success|ok|safe|unsafe|risk|warning|critical|added|removed|gone|kept|same|flat|unchanged|no change)\b/i;
  const out = [];
  document.querySelectorAll('*').forEach(el => {
    const cls = typeof el.className === 'string' ? el.className : '';
    if (!cls || !POLARITY_CLASS.test(cls)) return;
    const own = [...el.childNodes].filter(n => n.nodeType === 3)
      .map(n => n.textContent).join(' ').trim();
    if (!own) return;                          // must render its own text
    const visible = el.textContent.trim();     // includes child labels
    if (POLARITY_TEXT.test(visible)) return;
    out.push({
      sel: el.tagName.toLowerCase() + '.' + cls.trim().split(/\s+/).join('.'),
      text: visible.slice(0, 40),
      color: getComputedStyle(el).color
    });
  });
  const agg = {};
  out.forEach(o => { agg[o.sel] = (agg[o.sel] || 0) + 1; });
  return { candidateCount: out.length, bySelector: agg, candidates: out.slice(0, 20) };
}
```

**Read `bySelector`, not `candidateCount`.** One selector with 55 hits is a
component that never labels its direction, which is one fix. Fifty selectors
with one hit each is mostly noise.

**Test the visible text, not the direct text nodes.** An earlier version of this
probe read only `nodeType === 3` children and so could not see a label nested in
a child `<span>`. It scored a fixed page and a broken page identically at 81
candidates. If your counts do not move after a fix, suspect the probe before the
fix.

**Expect false positives, and do not tune them away.** Class names that describe
a *defect* or a *heading* rather than a UI state will match: `.light-fail`,
`.dark-fail`, `.verdict.v-bad` all surfaced on real runs with perfectly clear
text. Widening `POLARITY_TEXT` to silence them also silences real findings.

Measured behaviour, two real pages:

| Page | Candidates | Real |
|---|---|---|
| Skill fixture | 3 | 1 (`span.status.good`) |
| Report before fixing | 81 | 71 across `.worse`, `.better`, `.num.up` |
| Same report after fixing | 18 | 0 material |

The 81 to 18 drop is the check. An unchanged count means nothing was fixed.


---

## 6. Status-pair luminance check

Run whenever two colors encode opposite states: good/bad, pass/fail, up/down.

Contrast tools compare each color to its **background**. Both can pass 4.5:1 and
still be the same brightness as **each other**, which means the only thing
separating them is hue. Greyscale printing, a cheap projector, and color vision
deficiency all erase hue and leave the pair identical.

```python
def lin(c):
    c = c / 255
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

def lum(h):
    h = h.lstrip("#")
    r, g, b = (lin(int(h[i:i+2], 16)) for i in (0, 2, 4))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b

def ratio(a, b):
    la, lb = lum(a), lum(b)
    return (max(la, lb) + 0.05) / (min(la, lb) + 0.05)

GOOD, BAD = "#47682d", "#8c3a28"
print(f"good vs bad: {ratio(GOOD, BAD):.2f}:1")   # measured 1.19:1
```

**Under about 3:1 between the pair, hue is doing all the work.** Fix it in one
of two ways, and prefer the first:

1. Add a text cue, so the color stops being load-bearing at all.
2. Widen the lightness gap between the two tokens, so the pair survives
   greyscale.

Both is better than either.

Colorblind simulation is a reasonable confirmation, but **do not quote a
specific simulated ratio**. Different simulators use different matrices and
disagree materially: on the pair above, one run reported 1.06:1 under
deuteranopia while the Machado 2009 severity-1.0 matrices give 1.20:1. The
conclusion is identical and the number is not. The pair-luminance figure above
needs no matrix and is reproducible, which is why it is the check.

For the record, that pair under Machado 2009: protanopia 1.59, deuteranopia
1.20, **tritanopia 1.03**. Tritanopia was the worst case and is the one people
forget to test.

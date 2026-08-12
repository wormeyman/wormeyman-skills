# Scripts

Four scripts. The first three run in the page via `evaluate_script`. The fourth runs in bash against a saved Lighthouse report.

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

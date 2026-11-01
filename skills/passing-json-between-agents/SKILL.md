---
name: passing-json-between-agents
description: >-
  Use when handing data to another agent, a sandbox, or an upload box as a
  file, especially when the fields need explaining. Also use when someone asks
  for comments in a JSON file, or when a .jsonc, .json5 or YAML file is about
  to be made for another tool, or when an upload fails with "File type is not
  supported".
---

# Passing JSON between agents

## Overview

The agent on the other end has none of your context. It may sit in a sandbox
with an upload filter and only a strict JSON parser. **Plain JSON, with the
notes stored as text fields inside it, is the one format that survives every
hop.** A file that explains itself needs no separate guide.

## The file

- Extension `.json`. Content is strict JSON: no comments, no trailing commas,
  no single quotes, no unquoted keys.
- Put the explanation in the data, beside the values:
  - `about`: one string. What the file is, where the figures came from, and
    any naming trap ("no plan is named 'Premium'; Premier Rx is meant").
  - `field_notes`: an object keyed by field name, one plain sentence each.
    Give the unit, what an empty list or `null` means, which field is the
    key to match on, and anything the reader must not work out for itself.
- Keep values typed: `6.30` not `"$6.30"`, `[4, 5]` not `"tiers 4 and 5"`.
- A `.md` copy of the notes for people is fine. The JSON must still stand on
  its own.

```json
{
  "about": "Two 2027 drug plans. Figures agree across the carrier guide and CMS.",
  "field_notes": {
    "plan_id": "Contract and plan number. Match on this, never on the name.",
    "monthly_premium": "US dollars per month, before any help.",
    "deductible_tiers": "Tiers the deductible applies to. An empty list means no deductible."
  },
  "plans": [
    {"plan_id": "S5884-176", "monthly_premium": 127.90, "deductible_tiers": [4, 5]}
  ]
}
```

## Before handing it over

1. **Check what the receiver accepts.** The Claude PowerPoint agent takes PDF,
   DOCX, DOC, XLSX, XLS, PPTX, POTX, PPT, CSV, TXT, JSON, MD, SKILL, PNG, JPG,
   JPEG, GIF and WEBP. Anything else fails at upload with "File type '.jsonc'
   is not supported", even if the content is fine.
2. **Check it with a strict parser**, not by eye:
   `jq empty file.json` or `python3 -m json.tool file.json > /dev/null`.
   Both fail on a comment or a trailing comma.
3. **A formatter is not a check.** `vp fmt --check` (Oxfmt) passed a `.json`
   file with a `//` comment in it, and failed valid JSON over layout alone.
   Use it for tidiness only.

## Common mistakes

| Mistake | What happens | Do this instead |
|---|---|---|
| Notes as `//` comments in a `.jsonc` file | Refused at upload; strict parsers reject it | `field_notes` inside the JSON |
| Someone asks for "comments in the JSON" | JSON has no comments | Say so, and use `field_notes` |
| A `.json5` extension, or "json5" in the name of plain JSON | Refused at upload, or the name promises syntax the file lacks | Name the file for its content. Plain JSON is already valid JSON5 |
| Notes only in a separate README | The README gets lost and the reader guesses | Notes in the JSON; README optional |
| Deleting the old file when the format changes | The person loses a file they never asked to lose | Write the new file beside it. Ask before removing anything |

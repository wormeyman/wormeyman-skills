---
name: cloudflare-migration-sweep
description: Use when asked which repos still need a Cloudflare migration or deprecation fix - a Cloudflare migration guide or changelog post (vitest-pool-workers to vitest-plugin, Miniflare 2, unstable_dev, Wrangler v1 or v3, Workers Sites, Pages to Workers, next-on-pages, pages-action, workers-types, deprecated Workers AI models, legacy KV routes, Service Keys, an API end-of-life date), or "find all my projects that use X" across every repo and org a GitHub account can reach.
---

# Cloudflare migration sweep

Find every repo that still needs a Cloudflare migration, across a whole GitHub
account and its orgs, then decide which findings are real before filing anything.

## Do not use GitHub code search for this

`gh search code` does not return every private repo, and says nothing about the
ones it skipped. In the sweep that produced this skill it returned zero hits for a
private repo whose `package.json`, `tsconfig.json` and `vitest.config.ts` all used
the package being searched for. An empty result looks exactly like a clean
account. Clone and scan instead - it is faster than it sounds (93 repos,
1.75 GB of history: 30 s to shallow-clone, 6 s to scan).

## Run it

Scratch space only - never point `--dest` at a folder that holds real work.

```bash
python3 scripts/fetch_repos.py --dest <scratch>/cf-sweep   # you + all your orgs; --owner to narrow
python3 scripts/scan.py --dest <scratch>/cf-sweep          # summary; --jsonl for file:line; --repo owner/name
```

`fetch_repos.py` refreshes existing clones on re-run, so a second sweep reads
current code. `scan.py` groups hits per repo by tier and catalog entry. Entry
numbers index `references/catalog.md`: docs link, the fix, and any deadline.
Check the catalog's build date against today; if it is months old, refresh it
(instructions at its top) before trusting a clean result.

For one specific guide the user pasted, find its entry in the catalog. If it
is not there, add a rule to `scan.py` and an entry to the catalog first.

## Triage every hit before reporting

The scan finds text. These are the ways text lies, all seen in real sweeps:

| Output | What it usually is |
| --- | --- |
| "Every hit is in a comment" section, or `<- every hit is a comment line` | A note about a migration already done. Open one to confirm, then drop it. |
| Tier `review` | A pattern shared with non-Cloudflare tools (`CF_API_KEY` is flarectl's too; `addEventListener('fetch')` is also a PWA). Read each. |
| `[archived]` | Cannot take issues. Report it; do not file. |
| `[fork]` | Probably upstream's code. Report it; ask before filing. |
| `[collaborator]` | Someone else's repo. Report it; ask before filing there. |
| Tier `optional` | Cloudflare recommends it; nothing breaks. Report separately and let the user choose. |

Then read **every repo in the "read these by hand" list** at the end of the
summary. Those mention Cloudflare but matched no rule, which is where the misses
are: a deploy documented only in a README, a script type the rules do not cover,
a pattern nobody has written a rule for yet. When a miss turns out to be real,
add the rule to `scan.py` so the next sweep catches it.

The scan reads each repo's default branch only. It cannot see other branches, or
account-level state: Service Keys used by other tools, Vectorize V1 indexes, D1
alpha databases, dashboard-built Pages projects. Say so in the report rather
than implying a clean account.

## Before filing

- Search the repo's issues first (`gh issue list --state all --search ...`).
  A planned migration often already has one.
- Separate **required** (removed, deprecated, or dated) from **optional** in the
  report, and put the optional ones to the user as a choice.
- Give file:line on the default branch at a named commit, the exact change, and
  a "done when" the next person can check.

## When doing the migration

- Cloudflare codemods replace names inside comments too, so a comment can end up
  describing a version that never existed. Read the whole diff, not just the
  code lines.
- The new package's types may flag further deprecations the old one did not.
  Run the type check and read its warnings, not just its errors.
- A lockfile `allowScripts` (or pnpm `onlyBuiltDependencies`) that names
  `workerd@<exact version>` needs the new version, or its install script is
  skipped.

## `compatibility_date` is not a migration

Old dates are supported forever. Raising one turns on every runtime behavior
change dated in between, in production, on the next deploy - so it is its own
change, never bundled with a package migration.

The local test runtime caps it: the Vitest plugin bundles one workerd, and a
date newer than that build knows fails every test with
`ERR_FUTURE_COMPATIBILITY_DATE` (or `ERR_RUNTIME_FAILURE` on older plugins).
Find the cap by trying the date and the day after. To see what a raise turns
on, read `src/workerd/io/compatibility-date.capnp` at the workerd tag in use
(`compatEnableDate` and `impliedByAfterDate` lines) - it can be ahead of the
docs page.

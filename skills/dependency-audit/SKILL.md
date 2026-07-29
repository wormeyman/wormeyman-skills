---
name: dependency-audit
description: Audit a project's dependencies for available updates, removals, security issues, and major-version features worth adopting. Use this whenever the user asks what can be updated, upgraded, removed, replaced, or is outdated; asks whether a major version would bring useful new features; asks to review the packages, libraries, crates, gems or dependencies in a project; or mentions dependency hygiene, supply-chain risk, abandoned packages, or automated update tooling like Dependabot or Renovate - even if they never say the word "audit". Also use it when planning an upgrade batch, to decide what belongs in it.
---

# Dependency audit

## Why this needs judgement at all

Most of what people ask for here is already answered by tools. `npm outdated`
lists versions. `knip` finds unused packages. `npm audit` finds advisories.
Renovate does all three forever, unattended. If the deliverable is a list of
version numbers, a model is a slow and unreliable way to produce it.

The parts a tool cannot answer are the whole value of doing this by hand:

1. **Would _this_ codebase actually use what the new major brings?** A changelog
   says what changed. Only reading the code says whether it matters here.
2. **What in _this_ repo forbids the obvious upgrade?** Nearly every mature
   project holds something back on purpose, and the reason is rarely in the
   package. It is in a doc, an issue, or somebody's head.

An audit that misses the second kind is worse than no audit: it confidently
recommends work the project already considered and rejected, or work it is
technically unable to apply. That wastes the reviewer's time and, worse, trains
them to skim the next one.

So the shape of this skill is: **fill in what the tools cannot know first, then
let the tools do their own job, then reason only about what is left.**

## Step 0 - fill the four slots

Do this before running anything. Derive each slot from the repo, then state it
back explicitly.

**Slot 1 - Constraints and hazards.** What is deliberately held back, pinned, or
coupled, and why. Look in `CLAUDE.md` / `AGENTS.md` / `CONTRIBUTING.md`, in
comments next to pins, and in closed issues and PR descriptions.

Treat every documented reason as **possibly stale**. The circumstance that
justified a pin often expires without anyone editing the doc, and a constraint
that has been corrected once will be corrected again. For each constraint say
whether you re-derived it or are taking it on trust - those are different claims
and the reader needs to know which they are getting.

**Slot 2 - Update mechanism.** How does a change actually get applied here? Some
projects forbid a blanket `update`/`up` because transitive re-resolution breaks
something unrelated to the named package. Some enforce a minimum release age.
Some pin exact and some prefer ranges. **Every recommendation you make has to be
expressible in this project's mechanism**, or it is not a recommendation, it is
a wish.

**Slot 3 - In flight.** Open PRs and issues that touch dependencies. Check with
`gh pr list` and `gh issue list`, not just the working tree. Say what to treat
as already done. Recommending a swap that an open PR already performs is the
single most common way one of these reports gets dismissed.

**Slot 4 - Settled.** Decisions already taken, with their issue or commit
reference: "X was considered and deliberately kept - see #40." An audit that
re-proposes a rejected idea, with no sign it knows the idea was rejected, reads
as untrustworthy even where it is right.

**An empty slot is a finding, not a blank.** If you looked and there genuinely
are no held-back versions, say "no constraints documented" - that is useful and
slightly alarming information. What you must not do is skip the slot silently,
because "I found nothing" and "I did not look" produce the identical empty
section and the reader cannot tell them apart. If a slot needs the user to fill
it, ask before running the analysis rather than after.

## Step 1 - let the tools answer what they can

Run these before reasoning about anything. See `references/ecosystems.md` for
the commands per ecosystem (npm/pnpm/yarn, cargo, pip/uv, go, GitHub Actions,
and the non-package toolchain).

Use **absolute paths in every command**. Working directories persist between
calls, and a stale `cd` silently turns a glob into an empty result - which reads
exactly like a clean report. That failure mode is quiet and has produced wrong
"nothing to remove" conclusions.

For unused dependencies specifically, run a real tool (`knip`, `depcheck`,
`cargo-udeps`) and report its output. **Grep is not a substitute.** It cannot
see a package that is declared and never imported - which is the single most
common removable thing - and it misses dynamic imports and re-exports.

If a check needs an install or a write to verify, say so and stop, rather than
mutating a repo you were asked to inspect.

## Step 2 - the four questions, per major version

This is the part worth your time. For every major available, answer:

- **What it concretely adds or fixes.** From the changelog or release notes. Not
  inferred from the version number, and not from memory - major version
  contents are exactly the kind of fact that drifts.
- **Whether this codebase would use it.** Cite the file that would change, or
  say "no benefit here" plainly. A major that brings nothing relevant is a
  perfectly good answer and deprioritising it is a real result, so do not pad it
  into sounding valuable.
- **Migration cost, and what specifically breaks.**
- **What test coverage exists for the affected code, and whether a regression
  would actually be caught.** If nothing covers it, say so - that is usually the
  real risk, and it is invisible in every version table.

## Step 3 - the report

```
## Slots
Constraints / Update mechanism / In flight / Settled - each stated, empty ones named as empty.

## Inventory
Table: package | workspace | current | latest | publish date | gap | verdict
Verdicts: safe / needs care / blocked-by-constraint / don't.

## Majors worth taking
The four answers each.

## Majors not worth taking
One line each. As useful as the list above - it stops the next audit relitigating them.

## Removable
Declared-but-unused, and newly redundant (superseded by a platform or built-in API).

## Unmaintained vs merely old
These are different. A stable package with no releases in two years may be finished
rather than abandoned. Check issue activity and maintainer response, not just the date.

## Security
Split dev-only from runtime - they carry very different urgency.

## Automation
Is Dependabot or Renovate configured? If not, recommend one sized to this repo.

## Batches
Each sized to one PR, ordered by risk, expressed in the project's real update mechanism.
Name the verification gate that must pass for each.
```

## Discipline

**Separate what you verified from what you inferred.** Quote the command for
anything verified. This matters more here than in most tasks, because version
claims are cheap to state and expensive to be wrong about - a confident, wrong
"safe to bump" costs a broken build and the reader's trust in everything else in
the report.

**If something is boring, say so briefly rather than padding it.** A long report
where the important finding is buried in paragraph nine is a worse artifact than
a short one.

**Do not mutate.** No installs, upgrades, lockfile writes, branches, commits or
PRs. The deliverable is the report; applying it is a separate decision the user
makes after reading.

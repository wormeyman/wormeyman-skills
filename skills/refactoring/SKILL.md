---
name: refactoring
description: Evidence-driven refactoring assessment and execution for any language. Use this whenever the user wants code cleaned up, simplified, restructured, deduplicated, or made more readable - and also when they say "this file is a mess", "reduce the complexity here", "we have tech debt", "DRY this up", "split this god object", "is this worth refactoring?", or ask for a refactor survey of a repo. Use it BEFORE adding a feature to code the user calls messy, so the restructuring lands as its own reviewable step. Finds candidates from git co-change evidence rather than by eyeballing similarity, checks the test safety net is strong enough to make behavior preservation real, and knows the cases where duplication is deliberate and must be left alone (forks tracking upstream, ports of an external spec, generated code). Concluding "no refactor needed" is a valid and valuable result.
---

# Refactoring

Refactoring changes structure while preserving behavior. That definition carries the whole discipline: if behavior changed, it was not a refactor, and it needs the review and testing a behavior change gets.

**The rule that decides most calls:** refactor to remove *knowledge* duplication and complexity that is impeding work **now**. Everything else is churn, and churn on working code is a net loss - it burns review attention, invalidates people's mental maps, and risks a regression to fix nothing.

The hardest part is not performing a refactor. It is deciding which code deserves one. Most of this skill is about that.

## Precondition: can you even tell if you broke something?

Before proposing any change, establish these three. Skipping them is how refactors become outages.

**1. A passing baseline, and the command that proves it.** Run the repo's verification command and see it pass *before* you touch anything. Record what it is and how long it takes. If it does not pass now, stop - you cannot distinguish your breakage from the existing breakage.

This does not require TDD. Any trustworthy passing baseline works: a unit suite, integration tests, golden/approval files, fixture oracles, a characterization harness you write first. What matters is that it would *fail* if you changed behavior.

**2. An honest read of what that baseline actually proves.** This is the step most refactoring advice omits, and it is the one that decides whether "behavior-preserving under existing tests" means anything. Ask:

- Do tests exist for the specific code you want to move? Not the module - the code.
- Do they assert on *behavior and output*, or just that nothing threw?
- Would they fail if you deleted a branch inside the code you are about to restructure?

If you cannot answer yes, you have three options, in order of preference: write characterization tests first (capture current behavior as-is, even if it looks wrong - you are pinning it, not blessing it); restrict yourself to refactors the compiler or IDE can verify mechanically (rename, move, extract with tooling on a typed language); or leave it alone and say why.

A quick empirical check when unsure: **delete a line or invert a condition inside the target code and confirm something goes red.** If everything stays green, the safety net has a hole exactly where you were about to work. Put the line back.

**Check what the CI gate actually runs, not what tests exist.** These are routinely different, and the gap is invisible until it costs you. A repo can have hundreds of end-to-end specs that never run in CI because they need a dev server, a display, or a licensed binary - so a green pipeline proves only the fraction that runs unattended. Read the workflow file, compare it to the test directories, and if the real coverage lives in a suite CI skips, run that suite yourself before and after. Say in your report which suite you actually ran.

**Know what kind of failure your baseline produces.** Snapshot, golden-file and approval tests are excellent safety nets - they fail on any behavior change at all - but they fail *en masse*. If a refactor perturbs iteration order, tie-breaking, or floating-point accumulation, you get thousands of diffs rather than one clear message. That is the net working, not a reason to accept the diff. Never bulk-accept snapshots to make a refactor pass; a snapshot change means behavior changed, which means it was not a refactor.

**3. A clean tree, committed.** Commit the working baseline before restructuring. Then a bad refactor is `git reset`, not an archaeology exercise, and the diff you eventually present contains only the restructuring.

## Step 1: Find candidates from evidence, not appearance

Similar-*looking* code is the most common false lead in refactoring. Two files can share a shape because they do the same job, or because they solve parallel problems that will drift apart. Merging the second kind couples things that want to move independently, and you usually discover this months later when every change to one forces an awkward change to the other.

The question that separates them is **"would these change together?"** - and you do not have to guess, because git already recorded the answer.

### The co-change measurement

Run the bundled script. It works on any language, because it reads history, not syntax:

```bash
scripts/co-change.sh <repo> "12 months ago" 3 '^src/'
```

It ranks file pairs by SUPPORT (commits touching both) and JACCARD (support normalized by how busy each file is, so a hot file does not pair with everything). Read the header comment for caveats - renames, deletions, and young repos each distort it.

**Interpreting the ranking:**

| Pattern | What it means |
| --- | --- |
| High support, high jaccard | Strong coupling. The top candidates - go read these. |
| High support, low jaccard | One file is just busy. Probably coincidence. |
| Low support, looks like a twin | **Parallel evolution. Leave it alone.** The strongest result this gives you. |

Then, for a specific file, see what moves with it:

```bash
git log --follow --format=%H -- <file> \
  | while read c; do git show --name-only --format= "$c"; done \
  | sort | uniq -c | sort -rn | head -20
```

### Coupling is not automatically a defect

This is the nuance that keeps the tool from generating busywork. A type and the function that maps it will co-change constantly, and that is **correct cohesion** - they are one concept in two files. Co-change tells you where knowledge is *shared*; you still have to judge whether sharing it there is appropriate.

What you are hunting is co-change **plus** one of:
- the same rule literally written out in both places (change one, the other silently disagrees),
- coupling *across* a boundary that was supposed to be independent (a UI component and a rendering engine both encoding the same capability matrix),
- a pair that co-changes only because a third thing is missing - the concept they share has no home yet.

### Other candidate sources, in rough order of value

- **Literal repetition of a rule.** The same constant, predicate, or formula written out in three or more places, especially when it must stay consistent with a fourth definition elsewhere. Grep for a distinctive fragment and count the hits.
- **Churn × size.** Files that are both large and frequently edited are where structure costs the most: `git log --since="12 months ago" --name-only --format= | sort | uniq -c | sort -rn | head -20`.
- **The change you are about to make.** If a feature requires touching five files in the same way, that shape is the duplication - and this is the one case where refactoring immediately before the feature is clearly right.
- **Bug clusters.** Repeated fixes in one area often mean the structure invites the mistake.

Note what is *not* on this list: raw file length and raw complexity scores. Both are weak signals on their own - see "leave it alone" below.

## Step 2: Classify what you found

| Priority | Meaning | Typical |
| --- | --- | --- |
| **Critical** | Fix now | Knowledge duplication that must stay consistent; shared mutable state; control flow so nested the invariants can't be seen |
| **High** | This session | Unnamed magic values; names that mislead; one function doing several unrelated jobs |
| **Nice** | If you are already there | Minor naming, single-use helpers, ordering |
| **Skip** | Leave it | Clean enough, or on the exception list below |

Prefer the Critical items and stop. A refactor PR that fixes one real thing gets reviewed properly; one that also renames forty variables does not.

### DRY is about knowledge, not characters

**Abstract when** the duplicated thing is one *concept* - same meaning, would change together, and the shared name would be obvious to a reader.

**Keep separate when** the similarity is structural - different concepts that happen to look alike, evolving independently, where coupling them would confuse. Two `for` loops with the same shape are not duplication. Two implementations of one business rule are, even if they look nothing alike.

## Step 3: The exceptions - duplication that must stay

Before extracting anything, check whether the repetition is deliberate. Collapsing these actively makes the codebase worse, and each has burned someone before.

**Code mirroring an external source of truth.** Ports of a spec, a game's data files, an RFC, another system's schema. If the structure mirrors an upstream authority, keeping it parallel is what makes the next version diff readable - you can put the two side by side and see what changed. A clever abstraction destroys that, and it is how version-skew bugs survive review. Signals: comments citing an external version, files named after upstream ones, a pinned reference directory or submodule.

**Forks that merge upstream.** If the repo tracks an upstream remote and pulls from it, restructuring shared files converts every future merge into conflict resolution. Check `git remote -v` and whether the branch merges from upstream. Refactor freely in code you added; be conservative in code you inherited.

**Generated code.** Fix the generator or the template, never the output. Look for "do not edit" headers, `.g.`/`.generated.` names, or a build step that rewrites the file.

**Code with a second compilation or transpilation target.** If the source is also cross-compiled - to another language, to WASM, to an embedded runtime - then the *idioms available to you are a subset of the language's*. A refactor toward what is idiomatic can silently break the other target, and the failure often surfaces at transpile time or at runtime on the other platform rather than in the test suite. Before modernizing anything, find out whether constructs are banned and why. Deliberately hand-rolled replacements for standard-library types usually mean exactly this, or a measured performance need; either way they are not naivety waiting to be tidied.

**Structure that looks redundant but encodes ordering.** Two loops that could obviously be one, a value returned alongside another that could be recomputed, a separate plan-then-apply pass. These read as pure simplifications and often type-check perfectly - and collapsing them can change *when* things happen, which is a behavior change that only a test asserting on ordering or intermediate state would catch. If nothing explains why the structure is split, look for a comment, a linked issue, or a test name before assuming it is accidental.

**Deliberate performance duplication.** Inlined, unrolled, or specialized code paths. If there is a comment or benchmark explaining it, treat that as binding; if you think it is obsolete, measure before collapsing.

**Test code plays by different rules.** Duplication in tests is often correct: a test sharing a helper with the code under test can stop detecting the bug it exists to catch, and over-abstracted tests are hard to read at the moment of failure, which is exactly when readability matters. Prefer explicit and repetitive over clever in tests.

**Comments recording *how* something was determined.** When code moves, its comments move with it, intact. Comments that record a measurement, a citation, or a previously-held wrong belief are often the most valuable thing in the file and cannot be reconstructed.

## Step 4: Execute in small, separately verifiable steps

1. One structural change at a time. Extract *or* rename *or* move - not all three in one step, because when verification goes red you want to know which move did it.
2. Re-run the affected tests after each step. Run the full gate before committing.
3. Commit refactors separately from behavior changes, with a message saying what moved: `refactor: extract sweep-box geometry shared by five renderers`. A reviewer who sees "refactor" in the subject reads the diff differently, and mixing a behavior change into one is how bugs get waved through.
4. If a "refactor" needs a test changed to pass, stop. Either you changed behavior, or the test was asserting on structure rather than behavior. Both need saying out loud, not quietly absorbing.

## When not to refactor

- The structure is not impeding the work. Working code that is merely unfashionable is not a defect.
- **Speculative generality** - building for requirements that do not exist. The abstraction you invent before you have three real cases is usually wrong, and it is harder to remove than the duplication it replaced.
- It would change behavior. That is a feature or a fix; treat it as one.
- **Purely for testability.** If the only reason to extract is "so we can unit test it", prefer testing through the existing entry point. Extract for readability, real knowledge duplication, or separation of concerns.
- The code is under active investigation. If someone is mid-debugging or mid-measurement in that file, restructuring it destroys their bisect and their mental map. Wait.
- You cannot state the improvement in one sentence.
- Long functions that are *flat data* - lookup tables, config maps, transcriptions of an external source, exhaustive switches. Length is the wrong metric there; splitting them usually makes them harder to check against the source. Nesting and branching are what make code hard, not line count.

## Reporting "no refactor needed" is a real result

If the evidence says the code is fine, say so plainly and show the evidence - the co-change numbers, the test ratio, the absence of repeated rules. This is a valuable outcome: it converts a vague worry into a measured answer and stops the same question being reopened next month.

Equally, report the refactor you considered and **rejected**, and why. "These two files look like twins but share 0 commits, and they mirror two upstream files that version independently" saves the next person the whole investigation.

## Output format for a refactor survey

When asked to assess rather than execute, structure it as:

```
## Verdict
One or two sentences: refactor or not, and the single strongest reason.

## What is NOT worth refactoring (with evidence)
The tempting-but-wrong candidates, and the measurement that rules each out.
Put this first when the obvious-looking target is a false lead.

## Candidates, highest value first
For each: exact file:line citations, the evidence (co-change support, number
of duplicate sites), why it would change together, and the priority tier.

## Out of scope
Fragile or under-investigation areas, and what would need to be true to revisit.

## Constraints for whoever does the work
The verification command, the invariants, anything on the exception list.
```

## Checklist

- [ ] Verification command identified, and passing *before* any change
- [ ] Safety net assessed for the specific code being moved, not just the module
- [ ] Working baseline committed first
- [ ] Candidates backed by evidence (co-change, repeat count), not appearance
- [ ] Exception list checked - upstream/fork, generated, ported, perf, tests
- [ ] One structural change per step, verified between steps
- [ ] Full gate green before commit
- [ ] Refactor committed separately from any behavior change
- [ ] No test modified to make the refactor pass
- [ ] Comments carried over intact with the code they document
- [ ] The improvement is stateable in one sentence

## Repo-specific notes

`references/repo-notes.md` records verification commands and known constraints
for specific repositories. Read it when working in one of them; it saves
rediscovering the gate command and the do-not-touch areas.

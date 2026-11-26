---
name: pruning-tests
description: Finds the tests in a suite that are not worth their cost, proves each cut is safe by breaking the product code on purpose, and lands the cuts. Use when the user wants to remove useless, duplicate or low-value tests, says the suite is too big or too slow, asks "which of these tests can go?", "are our tests worth keeping?", or "can these browser tests be unit tests?", or wants an audit of a test suite before trimming it. Works for browser and end-to-end suites (Playwright, Cypress), where coverage tools cannot answer the question, as well as unit suites. Not for reviewing a single new test in a diff, and not for restructuring a CI pipeline.
---

# Pruning tests

A test earns its place when it can fail for a real bug that no cheaper test
would catch. Everything in this skill serves that one sentence. A test that
cannot fail is free to cut. A test whose bug another test already catches can
go once you have proved that other test really catches it. A test that guards
real logic through a slow browser may belong one layer down, in a unit test
that does the same job in milliseconds.

Slow is not a reason to cut. A slow test that is the only guard for a contract
stays. Speed is what you gain after the cuts are right, never the reason for
one.

## Ask before cutting anything

Measure first, then ask the user how far to go. The usual menu:

1. A read-only audit: grade every test, change nothing, let the user pick.
2. A campaign with a target, such as "a fifth of the browser suite's time".
3. One area only.
4. Leave it alone.

Recommend the read-only audit unless the user has already chosen. Deleting
tests is easy to do and hard to review afterwards, so the user picks the cuts
from evidence, not from a promise.

## Measure

- **Counts.** Test files and test cases, by the runner's own listing
  (`playwright test --list`, `vitest list`, `pytest --collect-only`), not a
  grep. Table-driven tests hide many cases behind one line.
- **Time per test, from CI.** Local times mislead: a desktop and a CI runner
  differ by 2x or more, and not evenly across tests. Pull the job logs of
  recent green runs and read each test's duration from them.
  `references/campaign.md` has the recipe. One run is noisy; use several.
- **Lines.** Tracked lines in tests, test helpers and product code
  (`git ls-files`). When tests pass about half of all lines, a full campaign
  usually pays.

## The cheap pass: tests that cannot fail

Before any grading, look for tests that would pass whether or not the product
works. These are the safest cuts and often the largest. The signs:

- No assertion at all, or assertions only inside an `if`, loop or `catch`
  that may never run. A test that collects errors into a report and never
  asserts on them is the common browser-suite form.
- The expected value comes from the code under test, or the setup and the
  assertion read the same object.
- The checked value is the same whether the code ran or not. An empty list
  that would also be empty if the click missed. A count that a missing dialog
  would also give.
- It asserts that a guard holds by restating the guard, instead of running
  the code the guard protects.
- It can only fail on a crash, a timeout or a missing selector.
- A quick screen: would it still pass if every function it calls returned
  `undefined`?

Each of these is a suspicion, not a verdict. Confirm it by breaking the
product code the test claims to guard (next section) and watching the test
stay green.

Look for the opposite too: a test that will fail one day with nothing wrong.
It reads data that changes on its own, such as today's date, the newest year
in a data file, or a figure someone updates every year. Mark it F and pin it
to a fixed copy of the data. Prove it the other way round: change the data,
not the code, and the old test goes red while the fixed one stays green.

## Grading

Every test gets one mark and one line of evidence:

| Mark | Meaning | Evidence it needs |
| --- | --- | --- |
| **R** keep | It guards something nothing cheaper guards | The contract, and the bug it catches |
| **F** fix | The contract is real but the assertion is weak | What is wrong, and how it would pass for the wrong reason |
| **M** move down | Real logic, tested at a costlier layer than it needs | The faster test that will hold it, written and proven first |
| **C** merge | Same contract as another test, or the same costly setup | The test that absorbs it, and which assertions move |
| **D** delete | Cannot fail, or fully covered elsewhere | The keeper, or why there is no contract |

For every C, M and D, record:

- **The keeper**, with its assertion quoted. A line number alone is not
  evidence.
- **How the keeper reaches the code.** This is the check most often skipped.
  Two tests can name the same feature and reach it by different paths: one
  loads data through the real entry point, the other decodes it and never
  calls that entry point. Write one line on what a green keeper does *not*
  prove.
- **The break that should prove it**: a one-line change in a named product
  file that the keeper must catch.
- **Seconds saved**, from the CI timings.

Grade on the assertions, not the test's title. Titles promise more than the
body checks, often.

Read the test's history too (`git log --follow -p`, the issue it cites). A
test that looks redundant may be the only regression test for a bug that
came back once.

## Prove each cut by breaking the code

Coverage says a line ran, not that anything checked it, and browser suites
have no coverage at all. So prove each cut directly:

1. Make the one-line break in the product code.
2. Run the keeper and the test being cut.
3. The keeper must fail, **on its own assertion**. The test being cut should
   stay green, which shows it added nothing for this bug. If it also fails,
   that is fine for a C or D: both caught it, and you keep one.
4. Put the code back exactly and confirm `git diff` is empty for that file.

`scripts/mutation_check.py` does all four steps for any runner that writes
JUnit XML, including Playwright. It runs the tests on the unbroken code first,
because a keeper that already fails proves nothing when it fails again.

Read the result carefully:

- **A failure is only a kill if it is the keeper's own assertion.** A timeout,
  a page that never loaded, or a setup error would have failed any test. That
  result is inconclusive, not a kill. Judge by the failure's headline, not
  its log: an assertion that polls and runs out of time still fails as that
  assertion, with "timeout" only in the log beneath it.
- **If every test fails the same way, suspect the environment**, not the
  break. Open one failure and read it.
- **Run the proof against the set of tests left after all the cuts in the
  batch.** Two cuts can each name the other as a keeper.
- **When two tests catch exactly the same breaks, cut one, not both.**
- **A table row needs a break of its own.** A row that feeds a different
  entity, rotation or data entry than its neighbours is its own test, even
  when they share a branch. Trim it only with a break that reaches that row's
  input alone (its data entry, or a branch only it takes) and that a remaining
  row still catches. A general break that every row catches proves nothing
  about the row you removed. If a count target can only be met by thinning
  such rows, fall short of the target instead.
- **Watch for caches that trust file times.** A break that keeps the file the
  same size, made within the same second, can run stale compiled code. The
  script moves the file time to prevent this; a hand edit does not.

If a break you expected to be caught survives every test, you have found a
gap, not a cut. Report it.

### Proving a fix

An F gets the same proof, in two runs. Break the code, and the old test stays
green: the weakness is real. Fix the test, make the same break, and the fixed
test goes red. With the script, that is `--expect-pass` on the old test, then
`--expect-fail` on the fixed one. If the old test goes red on the first run,
the claim was wrong; leave the test alone. Fixes save no time, and they are
often the most useful result of a run.

## Moving a test down a layer

Many slow browser tests check pure logic: a parser, a calculation, a rule.
They can move to a unit test that runs the same logic in milliseconds.

- Write the unit test first, and prove it with the same break.
- Keep one browser test for the wiring the unit test cannot see: the click
  reaching the handler, the result written back to the live screen.
- Check whether a unit test for this already existed and was lost.
  `git log -m --diff-filter=D --stat -- '*.test.*'` lists deleted test files.
  Keep the `-m`: without it, `git log` shows no files for merge commits, and
  a merge is where a test is most often dropped silently. Restoring a lost
  test is often the cheapest move of all.

## Speed without cutting

Before counting the seconds a cut would save, look at what each test sets
up. When every test starts its own database, emulator or browser context,
most of the suite's time is setup, and cuts barely move it. Sharing that
setup per file, with a reset before each test, keeps every assertion and can
save more than all the cuts together. One Vitest suite went from 188 s to
52 s that way with no test removed.

- Reset everything a test can write: every table, key and stored file, plus
  fake clocks and module-level state.
- Await background work (a `waitUntil`, a promise nobody awaits) before the
  next reset, or it lands in the next test's store.
- Keep a fresh instance for the few tests that need one, such as migrations
  applied in steps.
- Run each converted file in shuffled order (`vitest --sequence.shuffle`, or
  the runner's equivalent) to catch a test that leans on what an earlier one
  left behind.

This is a speedup, not a cut. Report it apart from the cuts.

## Landing the cuts

- Cut in small batches, grouped by the product area they guard.
- After each batch, look for what the cuts orphaned: helpers, fixtures and
  test-only hooks in the product with no remaining caller. Remove them in the
  same batch, after checking for other callers.
- Fix every comment and doc that names a deleted test as a guard. A README
  that says "test X catches this" is now wrong, and was sometimes wrong
  before.
- If the deleted test was the only thing a future reader would find, leave a
  short pointer to the keeper.
- If CI splits tests into shards by measured time, refresh those timings.
- Run the whole touched area, not just the keepers.

## Reporting what was saved

Quote seconds from per-test CI timings, the median over several runs where
possible. A refit total, or one run's wall time, moves with runner speed and
can hide or invent a saving. Say plainly which numbers came from one run.

Report tests that cannot fail as written but are worth fixing (F) separately.
They save no time, but they are often the most useful finding.

## Large suites

For a suite of hundreds of tests, split it by product area and give each area
to its own read-only agent, with a shared brief. Give them a frozen copy of
the code to read, such as a detached git worktree outside the repo folder,
because the lead will be editing the real checkout. `references/campaign.md`
has the brief, the ledger format and the timing recipe.

## Credits

The test-pruning skill this one grew from is OpenClaw's `test-audit`, written
by Peter Steinberger, with its campaign guide and junk-pattern list added by
Ayaan Zaidi
([openclaw/openclaw@80930af448](https://github.com/openclaw/openclaw/tree/80930af448ebabc84174146b56bc106d37fab3b4/.agents/skills/test-audit),
MIT). Matthew Blode adapted it as `test-audit` in
[mblode/agent-skills@f0b5cd4f](https://github.com/mblode/agent-skills/tree/f0b5cd4fc28a3598ecc01a8e480ea64c8a92d0c3/skills/test-audit)
(MIT), which is the version that was run on a real suite before this was
written. From them come the R/F/C/D ledger, one read-only agent per area,
and keeping only tests that guard something nothing else guards.

Smaller ideas, each reworded here:

- the "would it pass if every function returned `undefined`" screen, and
  quoting the keeper's assertion: darkroomengineering/cc-settings `audit`
- a line on what a green keeper does not prove: garrytan/gstack `test-audit`
- an all-killed run means a broken environment, and inconclusive is neither
  kill nor survival: CircleCI-Public/chunk-cli `chunk-testing-gaps`
- two tests with the same kills, cut one, not both: fallow-rs/fallow-skills
  `fallow-mutation`
- moving a test down a layer as a verdict of its own: thedavidweng/skills
  `ci-slim`
- tests that can fail only on a crash or a missing selector:
  obra/superpowers `writing-good-tests`
- keeping one cheap browser test for the wiring: openclaw/openclaw
  `openclaw-test-performance`

`NOTICE` holds the OpenClaw and mblode MIT notices. The README's design notes
say what this skill changes and why.

# Running a pruning campaign on a large suite

For a suite of hundreds of tests, one agent reading everything runs out of
context and starts skimming. Split the work, keep the readers away from the
edits, and keep every claim checkable.

## 1. Pin the starting point

- Record the commit, and confirm the tree is clean and matches the remote.
- Record counts and per-test CI timings (section 5) at that commit.
- Run the whole suite once. A test that fails before you change anything is
  a bug report, not a cut candidate: fix it or report it before going on.
- Unskip every skipped test once and run it. A skip with a real reason (a
  platform, a missing service) stays. A forgotten skip is either a passing
  test to keep or a failing one to report.

## 2. Split by product area

Group test files by the product code they guard (checkout, search, the
editor's dialogs), not by file name. Aim for 3 to 5 areas of similar CI time.
Every test file belongs to exactly one area.

## 3. Give readers a frozen copy

The lead edits the real checkout while the readers work, so give the readers
a copy that will not move under them:

```sh
git worktree add --detach ../<repo>-audit-<sha> <sha>
```

Put it outside the repo folder. A worktree inside it (for example under
`.claude/worktrees/`) can be picked up by the repo's own lint and type checks,
which then report hundreds of errors from files nobody changed. Remove it when
the readers are done: `git worktree remove ../<repo>-audit-<sha>`.

## 4. The brief

Write one brief file and point every reader at it, with only its area named
in the prompt. The brief says:

- Read only from the frozen worktree. Edit nothing. Run nothing that starts
  servers or browsers; the proofs come later, run by the lead.
- Read the repo's own notes on testing first (CLAUDE.md, CONTRIBUTING,
  AGENTS.md). Many apparently redundant tests are deliberate guards that a
  note explains.
- Read each test in full, its helpers, the product code it drives, its
  history, and any test elsewhere that covers the same thing, including the
  unit tests, which are far cheaper.
- Mark every test R, F, M, C or D (see SKILL.md), with an evidence line.
- For every C, M and D: the keeper with its assertion quoted, how the keeper
  reaches the code and what it does not prove, the one-line break that should
  prove the cut, and the seconds saved.
- Never name as a keeper a test that another area, or an earlier round, has
  already marked for cutting. List those in the brief.
- Return the ledger as text. Some hosts refuse a subagent's attempt to write
  report files, so the lead saves it.

Readers' "this other test covers it" claims are the part to check hardest.
They are usually right about *what* a keeper checks and sometimes wrong about
*how* it gets there.

## 5. Per-test timings from CI

The saving from a cut is that test's time on a CI runner. To get it:

1. List recent green runs of the main branch:
   `gh run list --workflow <ci> --branch <main> --status success --limit 9`.
2. For each run, list the test jobs and download each job's log:
   `gh api repos/<owner>/<repo>/actions/jobs/<job-id>/logs`.
3. Parse one line per passing test. Playwright's `list` reporter prints
   `✓  12 tests/foo.spec.ts:37:1 › title (829ms)`; other runners need their
   own pattern, or a JSON or JUnit report uploaded as an artifact.
4. Take each test's median over the runs. Runner speed varies by 2x or more
   between jobs, so one run is a rough guide at best. If the repo balances
   shards by duration, it may already fit a per-runner speed factor; reuse it.

Keep the parsed table (file, line, title, seconds) beside the ledgers. Every
"seconds saved" in a ledger should come from it.

## 6. Prove, then cut, one area at a time

- Run the baseline for every keeper and every cut test in the area once,
  unbroken.
- Run each proof with `scripts/mutation_check.py`. Never edit files while a
  browser suite is running against a dev server that reloads on change: the
  reload kills the running test and the failure looks like a kill.
- Delete the cut tests, their now-unused helpers and fixtures, and fix the
  comments and docs that named them.
- Run every touched test file in full, plus the repo's lint and type check.

## 7. After the cuts

- If CI shards tests by measured time, refit the timings from fresh CI logs
  with the repo's own tool, then check the shards come out even. A fit from a
  different set of runs moves every file's number, so compare the plan, not
  the total.
- If the campaign lasts long enough for the main branch to move, merge it in
  rather than rebasing, and for every test file the merge touched, check that
  a test the other side added still has a home.
- Check merges for lost tests in general. For each test file a merge deleted,
  name the contract it held and find where it lives now. A unit test dropped
  by a merge can leave slow browser tests as the only guard for years.

## 8. The report

- Counts and CI seconds before and after, from the per-test table.
- What was cut, grouped by why: could not fail, covered elsewhere, moved down.
- Every proof run, with its result, so a reviewer can repeat one.
- Fixes (F) and gaps found, listed apart from the cuts: tests that cannot
  fail as written, and breaks that no test caught.
- Anything the cuts left resting on a single test. Name it in the repo's
  notes so a later cleanup does not take it too.

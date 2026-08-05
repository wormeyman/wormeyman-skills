# wormeyman-skills

Agent skills I actually use, kept here so they survive a machine and so other
people can take them. All were written against real work rather than imagined
work, and the design notes below are the part worth reading - the skills
themselves are short.

The [skill format](https://code.claude.com/docs/en/skills) is a directory with a
`SKILL.md` carrying YAML frontmatter. It is read by Claude Code and by a growing
number of other agent tools.

## Skills

### [`dependency-audit`](skills/dependency-audit)

Audits a project's dependencies - what can be updated, removed, or replaced, and
whether a major version brings anything this codebase would actually use.

There are already several published dependency skills and they converge on the
same shape: inventory, then usage analysis, then changelog research, then a
phased plan. This one is built around a different observation.

**Most of that work belongs to tools, not to a model.** `npm outdated` lists
versions. `knip` finds unused packages. `npm audit` finds advisories. Renovate
does all three forever, unattended. If the deliverable is a table of version
numbers, an agent is a slow and unreliable way to produce it.

Two things tools cannot do, and they are the whole value:

1. Decide whether _this_ codebase would use what a new major brings. A changelog
   says what changed; only reading the code says whether it matters here.
2. Know what _this_ repo forbids. Mature projects hold things back on purpose,
   and the reason is rarely in the package - it is in a doc, an issue, or
   somebody's head.

So the skill's central mechanic is **four slots that must be filled before any
analysis begins**:

| Slot | What it captures | What it prevents |
| --- | --- | --- |
| Constraints | What is pinned or coupled, and why - treated as possibly stale | Recommending an upgrade that is deliberately held |
| Update mechanism | How a change actually gets applied here | Advice the project cannot execute |
| In flight | Open PRs and issues touching dependencies | Recommending work already underway |
| Settled | Decisions already taken, with references | Re-litigating a rejected idea |

An unfilled slot is reported as unfilled rather than skipped, because "I found
nothing" and "I did not look" otherwise produce the identical empty section.

Two real examples of what those slots catch. One project holds a types package
several majors back because the newer line targets a game version its committed
dataset does not match - upstream publishes a dedicated dist-tag for exactly
that, so the hold is the sanctioned path rather than neglect. Another forbids a
blanket `pnpm up` outright, because transitive re-resolution tips a config file
past TypeScript's comparison-depth limit and produces an error naming a package
that has nothing to do with it. Neither is discoverable from the dependency
tree.

The skill also insists on tools over grep for unused dependencies. Grep cannot
see a package that is declared and never imported, which is the single most
common removable thing - a mistake this skill exists partly because I made.

### [`session-handoff`](skills/session-handoff)

Turns everything learned in a session into one self-contained prompt for a fresh
session that knows nothing about the conversation, and puts it on the clipboard.

The design point is that the future reader has **zero context** - it cannot see
the chat, the scratchpad, or the reasoning. So the skill collects real state
first (branch, `git log`, what is uncommitted, what to read) rather than handing
back a template full of placeholders, and it leans on pointers: telling the next
session to read an authoritative file transfers more, more reliably, than three
paragraphs paraphrasing it.

It also warns against guessing. A wrong fact in a handoff is worse than an
omission, because the next session will act on it.

### [`refactoring`](skills/refactoring)

Decides whether code is worth refactoring, finds the candidates from evidence,
and knows the cases where duplication is deliberate and must be left alone.
Language-agnostic - it was built against a TypeScript SPA, a forked TS monorepo,
and a C# solution at the same time.

Published refactoring skills are not scarce, and they broadly agree on the
criteria: knowledge duplication is bad, deep nesting is bad, magic numbers are
bad, do not refactor speculatively. Those are correct. The gap is that they are
**criteria without a method**. Every one of them rests on "abstract what would
change together" and then leaves you to eyeball whether two files would change
together - which is exactly the judgement people get wrong, because
similar-looking code is the most common false lead in refactoring.

Git already recorded the answer. The skill ships
[`scripts/co-change.sh`](skills/refactoring/scripts/co-change.sh), which ranks
file pairs by how often they appear in the same commit, normalised so a busy
file does not pair with everything. Two files that look like twins and share
zero commits are parallel evolution, and merging them couples things that want
to drift apart. That measurement works identically on C# and TypeScript, which
is most of why the skill is language-agnostic at all.

Honesty about that script, though: when I A/B tested the skill, **the model
reached for git history on its own even without it**. The script makes the
measurement consistent and normalised rather than ad hoc, which is worth having
- but it is not where the skill earns its keep. That turned out to be somewhere
I did not predict, which is the next section.

The other three departures:

**It assesses the safety net before trusting it.** "Behavior-preserving under
existing tests" means nothing until you know what the tests prove. So the skill
checks coverage of the specific code being moved, and checks *what CI actually
runs* - one repo here has 159 end-to-end specs holding nearly all its real
coverage and none of them run in CI, so a green pipeline proves about 7 unit
files. It also suggests deleting a line to confirm something goes red, because
that answers the question in thirty seconds.

**It has an exception list for duplication that must stay.** Forks that merge
upstream, ports pinned to an external spec, generated output, and code that
cross-compiles to a second target. Two real cases from the repos it was built
on. In one, two loops that could obviously be one are deliberately separate;
collapsing them type-checks, reads as a pure simplification, and is a filed bug.
In the other, the C# transpiles to Lua, so LINQ, `yield return` and `try`/`catch`
are all forbidden - meaning the single most likely "cleanup" an agent would
propose compiles fine and silently breaks the build for the other target.

**"No refactor needed" is a result.** The survey that produced this skill
concluded that the most obvious-looking target in the codebase - seven pairs of
near-identical files - should not be touched, on the evidence that they share
0-2 commits each and mirror upstream files that version independently. Reporting
the refactor you considered and rejected, with the number that killed it, saves
the next person the whole investigation.

#### Does it actually help?

I A/B tested it: three realistic prompts against two real repos, each run twice,
with and without the skill, graded by a separate agent told to mark strictly and
verify claims against the repos. **18/18 assertions with it, 11/18 without**, at
a cost of about 25% more tokens and 80 seconds more wall time per run.

But the aggregate hides the finding, which is that the benefit is **narrow and
lopsided**:

| case | with | without |
| --- | --- | --- |
| Split a 2,700-line file (repo is a fork) | 6/6 | **1/6** |
| Modernise imperative C# (transpiles to Lua) | 6/6 | 5/6 |
| Survey a Vue app and rank the work | 6/6 | 5/6 |

Two of the three cases barely separate. In those, the constraint is written down
in the repo's own `CLAUDE.md` and README, and a careful agent finds it either
way - the skill adds one finding and a lot of runtime.

The first case is different in kind. Without the skill the model produced a
confident, well-evidenced, nine-module refactoring plan, having correctly
analysed churn and found the characterisation-test harness - and never once ran
`git remote -v`. The repo is a fork sitting 399 commits ahead of a live
upstream. It also called the safety net "unusually good" and staked its
recommendation on that, when the suite it was pointing at never runs in CI.

So the real lesson is **not** "measure co-change". It is that the constraints
which sink a refactor are disproportionately the ones **not visible in the
source**: whether the repo is a fork, whether a suite actually runs in CI,
whether a file is generated. Reading the code more carefully never surfaces
those, so the skill now spends thirty seconds on repository provenance before
it reads anything at all.

The eval also embarrassed one of my own claims, which is the other reason to run
one: I had predicted the co-change script would be the differentiator. It was
not.

## Install

Copy a skill into your skills directory:

```sh
git clone https://github.com/wormeyman/wormeyman-skills.git
cp -R wormeyman-skills/skills/dependency-audit ~/.claude/skills/
```

Per-project instead of globally: copy into `.claude/skills/` inside the repo.

Invoke by name (`/dependency-audit`), or just describe the task - the
`description` field in each skill's frontmatter is what decides whether it
triggers on its own.

## A note on writing skills

Both of these got shorter as they got better. The temptation is to write
exhaustive rules; what actually works is explaining _why_ something matters and
trusting the model with the rest. Where these do give a hard instruction - use a
real tool rather than grep, use absolute paths - it is because the failure mode
is **silent**. A stale working directory turns a glob into an empty result that
reads exactly like a clean report, and nothing in the output says otherwise.

## Licence

MIT - see [LICENSE](LICENSE).

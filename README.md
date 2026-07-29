# wormeyman-skills

Agent skills I actually use, kept here so they survive a machine and so other
people can take them. Both were written against real work rather than imagined
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

---
name: session-handoff
description: >-
  Generate a self-contained "resume this work" handoff prompt and copy it to the
  clipboard, so the user can paste it into a fresh session that has zero prior
  context. Use this whenever the user asks for a prompt to
  continue/resume/pick up work later, to "pbcopy a prompt", to hand off to a new
  session or agent, or says things like "give me a prompt to keep going in a new
  chat", "write me a handoff", "copy a prompt so I can resume this tomorrow", or
  "I want to start fresh on this" - even if they never say the words "skill" or
  "handoff". Trigger it any time the intent is capturing the current work state
  into a portable prompt for a future context-free session.
---

# Session handoff

## The job

Turn everything learned in this session into one **self-contained prompt** the
user can paste into a brand-new session (or hand to another agent) that knows
*nothing* about this conversation, then put that prompt on their clipboard.

The whole value is that the future session has **zero context**. It cannot see
this chat, your scratchpad, or your reasoning. If a fact isn't in the prompt (or
reachable from a pointer the prompt gives), it's gone. Write for that reader.

## Gather the real state first - don't hand back a template

A handoff prompt full of `<fill this in>` placeholders is useless. Before
writing, collect the concrete state so the prompt is specific and true:

- **Where the work lives** - repo path, current branch, and `git log --oneline -5`
  plus `git status --short` so you can name the exact commits and whether anything
  is uncommitted.
- **What's done** - the substantive results of this session, ideally anchored to
  commit hashes or file paths, not vibes.
- **What's next** - the specific next task, phrased as an instruction, not a mood.
- **What to read first** - the files, docs, and memories that hold the detail, so
  the prompt can point instead of dump.
- **Gotchas and conventions** - anything a fresh session would get wrong: how to
  run tests, "don't push", auth quirks, house style, tools to prefer.

Pull these from the actual conversation and the repo. When something is uncertain,
check it (a quick `git log`, an `ls`) rather than guessing - a wrong fact in a
handoff is worse than an omission because the next session will act on it.

## Lean on pointers, keep it portable

The best handoff is short but complete because it *delegates*. If the project
keeps notes or memory (design docs, `NOTES.md`, a memory system), tell the next
session to read them first rather than re-explaining their contents. A prompt that
says "read `docs/foo-NOTES.md` (authoritative) before touching anything" transfers
more, more reliably, than three paragraphs paraphrasing that file. Dump raw detail
only for things that live *nowhere but this chat*.

Use absolute paths so they're clickable and unambiguous in a fresh terminal.

## Prompt shape

Adapt to the work, but this structure covers most cases. Write it as if the user
is speaking to the next session in the first person - that's how they'll paste it.

```
I'm resuming work on <project> in <absolute repo path> (branch <branch>).

## Context
<1-3 sentences: what this is and the current goal>

## What's done
- <result, with commit hash / file path where it applies>
- ...

## Read these first (authoritative - don't re-derive)
- <absolute path> - <why it matters>
- memory/notes: <where the durable state lives>

## Next task
<the specific next step, concretely enough to start immediately>

## Conventions / gotchas
- <how to run tests / build>
- <constraints: e.g. don't push; branch first; style rules>
- <anything a cold start would trip on>
```

Drop sections that don't apply; add one if the work needs it. Match the target
tool's idiom - if the next session is Claude Code with skills/memory, say so and
point at them; if it's a plain chat, make the prompt fully self-standing.

## Put it on the clipboard

Write the prompt to a file, then pipe that file to the clipboard - this avoids
shell quoting mangling multi-line text and backticks, and leaves a copy the user
can re-grab:

```bash
# Pick whichever exists: pbcopy on macOS, clip.exe on Windows and WSL,
# xclip/wl-copy on a Linux desktop.
if command -v pbcopy >/dev/null; then pbcopy < /path/to/handoff-prompt.md
elif command -v clip.exe >/dev/null; then clip.exe < /path/to/handoff-prompt.md
elif command -v clip >/dev/null; then clip < /path/to/handoff-prompt.md
elif command -v wl-copy >/dev/null; then wl-copy < /path/to/handoff-prompt.md
elif command -v xclip >/dev/null; then xclip -selection clipboard < /path/to/handoff-prompt.md
else echo "NO_CLIPBOARD_TOOL"; fi
```

Prefer the session scratchpad directory for the file if one is defined; otherwise
a temp path is fine.

**Check the tool exists rather than assuming one.** `pbcopy` is macOS only;
`clip.exe` covers Windows AND WSL, because WSL executes Windows binaries. If none
is found, say so plainly and print the prompt in a copyable block - a clipboard
step that silently did nothing is the one failure the user cannot see, because
they only find out when they paste stale content into the fresh session.

## Close the loop

After copying, confirm it's on the clipboard and **show the prompt in the chat**
too, so the user can eyeball it before starting fresh and tell you to adjust
anything. Keep the confirmation to a line - the prompt itself is the deliverable.

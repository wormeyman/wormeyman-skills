---
name: asking-for-decisions
description: Put a decision to the user as an AskUserQuestion prompt with grounded options, never as a prose question. Use when you are about to ask the user anything whose answer changes what you do next - which approach to take, merge or hold, fix now or defer, which target to pick. Use it especially when finishing a long report, because that is where the habit breaks. Covers what counts as a decision, how to write options worth choosing between, and the tool mechanics: option count, headers, multiSelect, previews, and when not to ask at all.
---

# Asking for decisions

Every decision goes in an `AskUserQuestion` prompt. Never in prose.

A decision is any fork where the user's answer changes what you do next. Merge or hold. Which approach. Which file. Fix now or write it down for later. It is still a decision when you have a clear recommendation, and the recommendation goes in the prompt as the first option.

## Where this breaks

Not at the obvious forks. You handle those. It breaks at the end of a long report.

You have just finished something. You are writing it up. The prose is flowing. A question occurs to you and it feels like a natural closing sentence, so you write it as one:

> One thing I'd flag for later: the honest next test is pointing it at something you didn't build. One of the client sites would be a real trial.

That is a decision. It changes what happens next. It went out as a closing paragraph.

That example is real. It happened in the session that produced this skill, in a report about finishing a different skill, and the user had to ask for the prompt. Everything else in that session went into prompts correctly. The one that slipped was the one at the end of a long write-up, which is exactly where the rule says to watch.

So the check is mechanical. Before you send a long message, read your last paragraph. Anything in it the user could act on belongs in a prompt instead.

## What is not a decision

Do not ask about these. Asking too often is its own failure, and it trains people to stop reading the prompts.

- **Something with an obvious default.** Pick it, say you picked it in one line, and keep going.
- **Permission to continue.** "Should I proceed?" and "Does this look right?" are not decisions. If you have enough to act, act.
- **A fact you can check yourself.** Read the file. Run the command. Do not make the user your lookup table.
- **A choice that does not change your next action.** If you would do the same thing either way, there is nothing to ask.

## Writing options worth choosing between

The options are the whole value. A grounded option lets someone decide in five seconds. A vague one makes them do the thinking you were supposed to do.

**Put the real numbers in.** The measured value, the file that changes, the cost, the command that runs. Not "faster" but "cuts the run from 8 minutes to 90 seconds". Not "safer" but "does not touch the live site".

**Lead with your recommendation** and mark it `(Recommended)`. Having an opinion is not the same as not asking.

**Make the options genuinely different.** Two options that produce nearly the same outcome are one option with extra reading.

**Include the real do-nothing choice** when it exists. "Leave it and note it for later" is often the right answer, and leaving it out quietly pressures the user toward acting.

**Never restate the question as an option.** If the question is "should I merge this?", the options are not "merge" and "do not merge". They are the actual paths, with what each one costs.

Weak:

> Which approach do you want for the button color?
> - Option A: darken it
> - Option B: change the text color

Grounded:

> White on #00b899 computes to 2.53:1 and needs 4.5:1. Which fix?
> - Darken the green to #00856E (Recommended). Keeps white text, same hue family, computes to 4.58:1.
> - Keep #00b899, switch text to #0A2B24. Computes to 6.01:1 and preserves the brand color exactly, but a dark-on-green button will not match your other buttons.
> - Leave it and note it. It stays a known Level AA failure on the primary call to action.

## Batch, do not drip

Related decisions go in one call. The tool takes up to four questions. Asking them one at a time turns a ten second answer into four round trips.

Re-asking later is fine when something you learned actually changes the trade-off. Say what changed.

## Mechanics

- **2 to 4 options** per question. More than four means you have not decided anything yet.
- **Headers are 12 characters, hard.** "Button fix" works. "Which approach to take" does not.
- **`multiSelect: true`** when the choices are not mutually exclusive, and phrase the question so it is obvious more than one can be picked.
- **Previews** render as monospace blocks for side by side comparison. Use them for real artifacts: layout mockups, two versions of a function, color swatches. Not for preference questions where the labels already say everything. Single-select only.
- **Never write an "Other" option.** The tool adds one. Writing your own wastes a slot.
- **Descriptions carry the specifics.** The label is a handle, not the argument. Put the numbers in the description.

## Red flags

| Thought | Reality |
|---|---|
| "I'll just mention it at the end" | That is the failure mode. Put it in a prompt. |
| "It's obvious what they'll pick" | Then lead with it, marked Recommended, and still ask. |
| "A prompt feels heavy for this" | A prompt is one click. A prose question is a whole reply. |
| "I'll ask this one now and the rest after" | Batch them. Up to four in one call. |
| "I don't have numbers for the options yet" | Then you are not ready to ask. Go measure first. |
| "Should I proceed?" | Not a decision. Act. |

## A note on where this lives

This skill is the craft. The trigger belongs in `CLAUDE.md` or its equivalent, as a standing rule, because a skill has to be invoked and this behavior has to be automatic. Keep both. The rule fires every time; this file explains how to do it well.

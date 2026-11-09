---
name: python-quality
description: Use when setting up or tightening linting and type checking in a Python repo, when choosing between Pyrefly, ty, pyright, basedpyright and mypy, when adopting strict checks in an existing codebase without fixing everything first, or when AI-written Python should meet a standard automatically rather than by instructions.
---

# Python quality

Tools enforce the standard; prose does not. A rule a tool checks costs nothing until it fails, so spend effort on tools and enforcement, not on instructions or the last few percent.

## The setup

- **Type checker: Pyrefly with `preset = "strict"`.** Strict turns on every `implicit-any` check (unannotated parameters, empty containers, untyped lambdas). The default preset does not, which is why Pyrefly can look lax in a quick test. It checks a file in 0.1-0.4 s (pyright: 0.5-2 s). ty has no strict mode. basedpyright is the fallback.
- **ruff with a chosen rule list, never `ALL`.** `ALL` wants a docstring on every function, which is the last-few-percent cost. A good list: `E W F I UP B BLE C4 SIM PERF RET PL C90 PTH ARG ANN PGH RUF S`, plus `PT` for tests, which can ignore `S101` and `PLR2004`. Keep `requires-python` honest: at 3.14, `ruff format` writes `except A, B:`, which older Pythons cannot parse.
- **Versions: a range in `pyproject.toml`, exact in the lockfile.** Major for 1.x tools (`pyrefly>=1.4.1,<2`), minor for 0.x (`ruff>=0.17.4,<0.18`). New releases add rules, so upgrade in a commit of its own.
- **Enforce on every edit.** `python-quality-hook.py`, beside this file, is a Claude Code `PostToolUse` hook for `Edit|Write|MultiEdit`. It is silent when the edited file is clean and exits 2 with the errors otherwise. Its docstring says which repos it acts in. It needs Python 3.11+ and the repo's tools installed (a `uv.lock`, or `.venv/bin`). Register it once, globally or per project, not both, or it runs twice. Keep pre-commit or CI running the same checks.

## Existing code

Fix it if only a few lines are involved. Otherwise grandfather it: `ruff check --add-noqa`, and a Pyrefly baseline (`pyrefly check --update-baseline`).

- **Set `baseline-matching-mode = "concise-description"`.** The default modes match on file, rule and column. In a test, a new function's error took the slot of an old error that had just been fixed and stayed hidden. `"concise-description"` includes the function name, so it was reported.
- Put `baseline = "<file>"` in the config, not on the command line, so the hook uses it too. The path is relative to where Pyrefly runs, so run it from the repo root.
- Run the gate as `pyrefly check --error-stale-baseline`, and clean up with `--prune-baseline`. Otherwise a fixed error's entry stays and hides the error if it comes back. `RUF100` does the same job for `noqa` markers.
- Never run `ruff check --select RUF100 --fix`. With the other rules off, every marker looks unused, and ruff deletes them all.

## Script repos and migrations

- Folders whose scripts import their neighbours (`from plans import ...`) need `enable-fallback-search-path = true` in Pyrefly.
- **Never put one such folder on `search-path` or pyright's `extraPaths`.** Both are searched before a script's own folder, so another folder's `plans.py` silently resolves to that one. pyright reports it as `reportAttributeAccessIssue`, which repos often turn off for pandas. For pyright, give each folder its own `executionEnvironments` root.
- **Pyrefly imports `pyrightconfig.json`** when it has no config of its own, and `pyrefly init` writes the same thing out: `extraPaths` becomes `search-path` and turned-off rules become ignores. So a straight migration copies any such bug across. Write the Pyrefly config by hand.
- pyright and Pyrefly both skip dot folders like `.claude/`.
- Before replacing a tuned pyright setup, count Pyrefly's distinct error lines, not errors: one untyped dict can raise dozens from one expression. Typing the data is what finds bugs, whichever checker reads it.

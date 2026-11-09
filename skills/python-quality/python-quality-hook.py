#!/usr/bin/env python3
"""Claude Code PostToolUse hook: format, lint and type-check a Python file right after Claude edits it.

Needs Python 3.11 or newer (for tomllib) as `python3` on PATH.

Opt-in per repo, decided by the nearest folder above the edited file that has a pyrefly.toml or a
pyproject.toml:
  - a pyrefly.toml, or [tool.pyrefly] in pyproject.toml: ruff, then Pyrefly.
  - [tool.ruff] in pyproject.toml and a pyrightconfig.json beside it: ruff, then pyright, for a
    repo that keeps a tuned pyright setup.
Everywhere else it exits 0 and does nothing.

It runs the repo's own tools: `uv run --frozen` in a uv project (one with a uv.lock), otherwise
`.venv/bin/<tool>`. In an opted-in repo where a tool is missing it says so, rather than passing
silently.
  1. ruff format <file>            (silent)
  2. ruff check --fix <file>       (applies the safe fixes)
  3. pyrefly check <file>, or pyright <file>
When everything is clean it prints nothing, so it costs no tokens. When problems remain it prints
them to stderr and exits 2, which Claude Code feeds back to Claude to fix.
"""

import json
import subprocess
import sys
import tomllib
from pathlib import Path

MAX_LINES = 40  # keep the feedback short; the repo's full check lists the rest
TIMEOUT_S = 120
RUFF_CHATTER = ("Found ", "[*]", "No fixes available")  # summary lines, not problems


def project_root(file: Path) -> tuple[Path, str] | None:
    """The opted-in repo root and its type checker ("pyrefly" or "pyright"), or None."""
    for folder in file.parents:
        if (folder / "pyrefly.toml").is_file():
            return folder, "pyrefly"
        config = folder / "pyproject.toml"
        if config.is_file():
            try:
                tools = tomllib.loads(config.read_text()).get("tool", {})
            except (OSError, tomllib.TOMLDecodeError):
                return None
            if "pyrefly" in tools:
                return folder, "pyrefly"
            if "ruff" in tools and (folder / "pyrightconfig.json").is_file():
                return folder, "pyright"
            return None
    return None


def command(root: Path, tool: str) -> list[str] | None:
    """How to run `tool` in this repo: through uv for a uv project, else from its .venv, else None."""
    if (root / "uv.lock").is_file():
        return ["uv", "run", "--frozen", "--quiet", tool]
    local = root / ".venv" / "bin" / tool  # e.g. a requirements.txt repo with a plain .venv
    return [str(local)] if local.is_file() else None


def run(root: Path, cmd: list[str], *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 - the command is the repo's own tool, args are a file path
        [*cmd, *args],
        cwd=root,  # Pyrefly reads a baseline path relative to the folder it runs in
        capture_output=True,
        text=True,
        timeout=TIMEOUT_S,
        check=False,
    )


def lint_problems(root: Path, ruff: list[str], rel: str) -> list[str]:
    problems: list[str] = []
    # --force-exclude makes ruff honor the repo's excludes even for a file named on the command line
    fmt = run(root, ruff, "format", "--force-exclude", rel)
    if fmt.returncode != 0:
        problems.append(f"ruff format failed:\n{fmt.stderr.strip()}")
    lint = run(root, ruff, "check", "--fix", "--force-exclude", "--output-format", "concise", rel)
    if lint.returncode != 0:
        problems += [line for line in lint.stdout.splitlines() if line and not line.startswith(RUFF_CHATTER)]
        if lint.stderr.strip():
            problems.append(lint.stderr.strip())
    return problems


def pyrefly_problems(root: Path, pyrefly: list[str], rel: str) -> list[str]:
    result = run(root, pyrefly, "check", "--output-format", "min-text", rel)
    lines = (result.stdout + result.stderr).splitlines()
    # A misspelled config key is only a warning, and the setting is silently ignored
    problems = [line.strip() for line in lines if "WARN" in line and "key" in line.lower()]
    if result.returncode != 0:
        errors = [line for line in lines if line.startswith("ERROR")]
        problems += errors or [f"pyrefly exited {result.returncode}:\n{result.stderr.strip()[-800:]}"]
    return problems


def pyright_problems(root: Path, pyright: list[str], rel: str) -> list[str]:
    result = run(root, pyright, "--outputjson", rel)
    if result.returncode == 0:
        return []
    try:
        diagnostics = json.loads(result.stdout)["generalDiagnostics"]
    except (json.JSONDecodeError, KeyError):
        return [f"pyright exited {result.returncode}:\n{(result.stdout + result.stderr).strip()[-800:]}"]
    return [
        f"{rel}:{d['range']['start']['line'] + 1}: pyright {d.get('rule', 'error')}: "
        f"{d['message'].splitlines()[0]}"
        for d in diagnostics
        if d["severity"] == "error"
    ]


def main() -> int:
    try:
        event = json.load(sys.stdin)
    except json.JSONDecodeError:
        return 0
    tool_input = event.get("tool_input") or {}
    path = tool_input.get("file_path") or (event.get("tool_response") or {}).get("filePath")
    if not path or not path.endswith((".py", ".pyi")):
        return 0
    file = Path(path).resolve()
    found = project_root(file) if file.is_file() else None
    if found is None:
        return 0
    root, checker = found
    rel = str(file.relative_to(root))

    problems: list[str] = []
    ruff, types = command(root, "ruff"), command(root, checker)
    missing = [name for name, cmd in (("ruff", ruff), (checker, types)) if cmd is None]
    if missing:
        problems.append(
            f"{' and '.join(missing)} not installed in {root} (no uv.lock, no .venv/bin copy): "
            "install the dev tools so this repo's checks can run"
        )
    if ruff is not None:
        problems += lint_problems(root, ruff, rel)
    if types is not None:
        check = pyrefly_problems if checker == "pyrefly" else pyright_problems
        problems += check(root, types, rel)

    if not problems:
        return 0
    shown = problems[:MAX_LINES]
    more = len(problems) - len(shown)
    print(f"python-quality: {rel} still has problems (already formatted and auto-fixed):", file=sys.stderr)
    print("\n".join(shown), file=sys.stderr)
    if more:
        print(f"... and {more} more. Run the repo's full check in {root} for the rest.", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())

# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml>=6"]
# ///
"""Check every skill's frontmatter the way the strictest installer reads it.

Claude Code tolerates frontmatter that is not valid YAML. The `skills` CLI
behind skills.sh does not: it skips the skill with a warning, so a broken
description silently drops a skill from every `npx skills add` install. This
runs the same checks in CI, plus the naming rules from the Agent Skills spec
(https://agentskills.io/specification) and a check that the README and the
plugin manifests stay in step with the skills directory.

Run from the repo root: uv run scripts/validate_skills.py
"""

import json
import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
NAME_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")  # no leading, trailing or doubled hyphens


def frontmatter(text: str) -> str | None:
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return None
    for i, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            return "\n".join(lines[1:i])
    return None


def check_skill(skill_dir: Path) -> list[str]:
    where = f"skills/{skill_dir.name}"
    skill_md = skill_dir / "SKILL.md"
    if not skill_md.is_file():
        return [f"{where}: no SKILL.md"]

    raw = frontmatter(skill_md.read_text(encoding="utf-8"))
    if raw is None:
        return [f"{where}/SKILL.md: no frontmatter block between --- lines"]
    try:
        meta = yaml.safe_load(raw)
    except yaml.YAMLError as err:
        # the usual cause is an unquoted ": " inside the description
        return [f"{where}/SKILL.md: frontmatter is not valid YAML: {str(err).splitlines()[0]}"]
    if not isinstance(meta, dict):
        return [f"{where}/SKILL.md: frontmatter is not a mapping"]

    errors = []
    name, description = meta.get("name"), meta.get("description")
    if not isinstance(name, str):
        errors.append(f"{where}/SKILL.md: name is missing or not a string")
    else:
        if not NAME_RE.match(name) or len(name) > 64:
            errors.append(f"{where}/SKILL.md: name {name!r} must be 1-64 lowercase letters, digits and single hyphens")
        if name != skill_dir.name:
            errors.append(f"{where}/SKILL.md: name {name!r} does not match its folder")
    if not isinstance(description, str) or not description.strip():
        errors.append(f"{where}/SKILL.md: description is missing, empty or not a string")
    elif len(description) > 1024:
        errors.append(f"{where}/SKILL.md: description is {len(description)} characters, limit is 1024")
    return errors


def check_manifests() -> list[str]:
    errors = []
    for rel in (".claude-plugin/marketplace.json", ".claude-plugin/plugin.json"):
        path = ROOT / rel
        if not path.is_file():
            errors.append(f"{rel}: missing")
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as err:
            errors.append(f"{rel}: not valid JSON: {err}")
            continue
        if rel.endswith("marketplace.json"):
            if not data.get("name") or not data.get("owner") or not data.get("plugins"):
                errors.append(f"{rel}: needs name, owner and plugins")
            for i, entry in enumerate(data.get("plugins", [])):
                if not entry.get("name") or not entry.get("source"):
                    errors.append(f"{rel}: plugins[{i}] needs name and source")
        elif not data.get("name"):
            errors.append(f"{rel}: needs name")
    return errors


def main() -> int:
    skill_dirs = sorted(p for p in (ROOT / "skills").iterdir() if p.is_dir())
    errors = [e for d in skill_dirs for e in check_skill(d)]

    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    for d in skill_dirs:
        if f"(skills/{d.name})" not in readme:
            errors.append(f"README.md: no link to skills/{d.name}")

    errors += check_manifests()

    for e in errors:
        print(f"FAIL {e}")
    print(f"{len(skill_dirs)} skills checked, {len(errors)} problem(s)")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())

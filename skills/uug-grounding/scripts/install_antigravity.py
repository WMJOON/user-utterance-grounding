#!/usr/bin/env python3
"""Install global Antigravity skills/hook while preserving unrelated config."""
import json
from pathlib import Path
import sys


def install(skill):
    root = Path.home() / ".gemini" / "config"
    path = root / "hooks.json"
    # Invalid existing config is a failure, never replaced by an empty object.
    config = json.loads(path.read_text()) if path.exists() else {}
    if not isinstance(config, dict):
        raise ValueError("hooks.json must be an object")
    skills = root / "skills"
    skills.mkdir(parents=True, exist_ok=True)
    members = sorted(skill.parent.glob("uug-*"))
    for member in members:
        if not (member / "SKILL.md").is_file():
            continue
        link = skills / member.name
        if link.exists() and not link.is_symlink():
            raise FileExistsError(f"Existing skill directory: {member.name}")
    for member in members:
        if not (member / "SKILL.md").is_file():
            continue
        link = skills / member.name
        if link.is_symlink():
            if link.resolve() == member.resolve():
                continue
            link.unlink()
        link.symlink_to(member.resolve(), target_is_directory=True)
    config["uug-grounding"] = {"PreInvocation": [{"type": "command", "timeout": 10,
        "command": 'python3 "$HOME/.gemini/config/skills/uug-grounding/hooks/ug-antigravity-hook.py"'}]}
    path.write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n")
    print("Antigravity: UUG skills + PreInvocation installed (unrelated hooks preserved)")


if __name__ == "__main__":
    install(Path(sys.argv[1]).resolve())

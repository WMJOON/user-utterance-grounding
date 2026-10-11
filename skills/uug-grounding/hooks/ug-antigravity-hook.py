#!/usr/bin/env python3
"""Antigravity PreInvocation → UUG infer → ephemeral context (no dispatch)."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys

from context_contract import format_context

SKILL = Path(__file__).resolve().parents[1]
UG = SKILL / "scripts" / "ug.py"


def context(payload):
    if (os.environ.get("UUG_DISABLED") == "1" or os.environ.get("UUG_ENABLED") == "0"
            or os.environ.get("UUG_HOOKS_DISABLED") == "1"):
        return {}
    transcript = payload.get("transcriptPath")
    workspaces = payload.get("workspacePaths") or []
    cwd = workspaces[0] if workspaces else None
    if not isinstance(transcript, str) or not Path(transcript).is_file():
        return {}
    parser = SKILL.parent / "uug-pattern-analytics" / "scripts" / "tag_targets.py"
    spec = importlib.util.spec_from_file_location("uug_agy_turns", parser)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    turns = list(module._antigravity_turns(Path(transcript), cwd))
    # PreInvocation also runs after tool calls. Deliver once per new human input,
    # determined from transcript; no per-session state files or user text logs.
    if not turns or turns[-1]["responded"]:
        return {}
    prompt = turns[-1]["text"]
    cmd = [sys.executable, str(UG), "infer", "--log", prompt, "--transcript", transcript]
    if cwd:
        cmd += ["--session-dir", cwd]
    result = subprocess.run(cmd, text=True, capture_output=True, timeout=9)
    if result.returncode:
        return {}
    message = format_context(json.loads(result.stdout), cwd)
    return {"injectSteps": [{"ephemeralMessage": message}]} if message else {}


def main():
    try:
        payload = json.load(sys.stdin)
        result = context(payload) if isinstance(payload, dict) else {}
    except Exception as exc:
        # Never block an invocation or print a prompt/path-containing exception.
        print(f"uug-antigravity: {type(exc).__name__}", file=sys.stderr)
        result = {}
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()

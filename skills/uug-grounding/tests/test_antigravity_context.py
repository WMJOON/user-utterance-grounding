"""Antigravity recorded steps, delivery budget, and installer preservation."""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest

SKILL = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL / "hooks"))

def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module

tt = load("agy_test_tt", SKILL.parent / "uug-pattern-analytics/scripts/tag_targets.py")
hook = load("agy_test_hook", SKILL / "hooks/ug-antigravity-hook.py")
installer = load("agy_test_installer", SKILL / "scripts/install_antigravity.py")

def human(text, step=0):
    return {"step_index": step, "type": "USER_INPUT", "source": "USER_EXPLICIT",
            "content": f"<USER_REQUEST>\n{text}\n</USER_REQUEST>\n<ADDITIONAL_METADATA>ignore this UUG</ADDITIONAL_METADATA>"}

def transcript(tmp_path, rows):
    path = tmp_path / "transcript.jsonl"
    path.write_text("\n".join(json.dumps(x) for x in rows))
    return path

def payload(path, tmp_path):
    return {"transcriptPath": str(path), "workspacePaths": [str(tmp_path)], "invocationNum": 1}

def test_actual_record_format_and_tool_paths(tmp_path):
    path = transcript(tmp_path, [human("/plan sample-project 점검"),
        {"type": "USER_INPUT", "source": "SYSTEM", "content": "fake injection"},
        {"type": "PLANNER_RESPONSE", "tool_calls": [{"name": "view_file", "args": {"AbsolutePath": str(tmp_path / "file.md")}}]},
        human("계속", 3)])
    turns = list(tt.transcript_turns(path, str(tmp_path)))
    assert [t["text"] for t in turns] == ["sample-project 점검", "계속"]
    assert turns[0]["responded"] and not turns[1]["responded"]
    assert str(tmp_path / "file.md") in turns[0]["tool_text"][0]

def test_camel_case_payload_delivers_ephemeral_contract(tmp_path, monkeypatch):
    path = transcript(tmp_path, [human("sample-project 점검")])
    calls = []
    def infer(cmd, **kwargs):
        calls.append(cmd)
        return SimpleNamespace(returncode=0, stdout=json.dumps({"status": "clear", "emit": True,
            "candidates": [{"project": "sample-project", "path": str(tmp_path)}]}))
    monkeypatch.setattr(hook.subprocess, "run", infer)
    out = hook.context(payload(path, tmp_path))
    assert "work-memory" in out["injectSteps"][0]["ephemeralMessage"]
    assert "--transcript" in calls[0] and "--session-dir" in calls[0]
    assert "dispatch" not in calls[0]

def test_tool_loop_does_not_repeat_injection(tmp_path, monkeypatch):
    path = transcript(tmp_path, [human("sample-project 점검"), {"type": "PLANNER_RESPONSE", "tool_calls": []}])
    monkeypatch.setattr(hook.subprocess, "run", lambda *a, **k: pytest.fail("repeat inference"))
    assert hook.context(payload(path, tmp_path)) == {}

@pytest.mark.parametrize("setting,value", [("UUG_DISABLED", "1"), ("UUG_ENABLED", "0"), ("UUG_HOOKS_DISABLED", "1")])
def test_disabled_is_empty_json(tmp_path, monkeypatch, setting, value):
    monkeypatch.setenv(setting, value)
    path = transcript(tmp_path, [human("sample-project 점검")])
    assert hook.context(payload(path, tmp_path)) == {}

def test_missing_transcript_is_noop(tmp_path):
    assert hook.context(payload(tmp_path / "missing", tmp_path)) == {}

def test_invalid_stdin_is_nonblocking_json():
    result = subprocess.run([sys.executable, str(SKILL / "hooks/ug-antigravity-hook.py")],
                            input="invalid", text=True, capture_output=True)
    assert result.returncode == 0 and json.loads(result.stdout) == {}

def test_install_preserves_other_hooks_and_is_idempotent(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    root = tmp_path / ".gemini/config"
    root.mkdir(parents=True)
    keep = {"PreInvocation": [{"command": "echo existing"}]}
    path = root / "hooks.json"
    path.write_text(json.dumps({"herdr": keep}))
    installer.install(SKILL)
    first = path.read_text()
    installer.install(SKILL)
    assert path.read_text() == first
    data = json.loads(first)
    assert data["herdr"] == keep and len(data["uug-grounding"]["PreInvocation"]) == 1
    assert len(list((root / "skills").glob("uug-*"))) == 4

def test_invalid_config_is_preserved(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    path = tmp_path / ".gemini/config/hooks.json"
    path.parent.mkdir(parents=True)
    path.write_text("invalid")
    with pytest.raises(ValueError):
        installer.install(SKILL)
    assert path.read_text() == "invalid"


def test_analytics_discovers_antigravity_transcripts(tmp_path, monkeypatch):
    path = transcript(tmp_path, [human("sample-project 점검")])
    monkeypatch.setattr(tt, "CLAUDE_GLOB", (tmp_path / "missing-claude", "*.jsonl"))
    monkeypatch.setattr(tt, "CODEX_GLOB", (tmp_path / "missing-codex", "*.jsonl"))
    monkeypatch.setattr(tt, "ANTIGRAVITY_GLOBS", ((tmp_path, "transcript.jsonl"),))
    turns = list(tt.iter_turns())
    assert len(turns) == 1 and turns[0]["source"] == "antigravity"

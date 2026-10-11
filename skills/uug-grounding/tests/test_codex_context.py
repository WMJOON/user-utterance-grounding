"""Codex transcript → continuation → delivered context regression tests."""
import importlib.util
import json
import sys
from pathlib import Path

SKILL = Path(__file__).resolve().parents[1]

def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module

tt = load("context_tt", SKILL.parent / "uug-pattern-analytics/scripts/tag_targets.py")
ug = load("context_ug", SKILL / "scripts/ug.py")
contract = load("context_contract", SKILL / "hooks/context_contract.py")

def message(text):
    return {"type": "response_item", "payload": {"type": "message", "role": "user",
            "content": [{"type": "input_text", "text": text}]}}

def event(text):
    return {"type": "event_msg", "payload": {"type": "item_completed", "item": {
        "type": "UserMessage", "content": [{"type": "text", "text": text}]}}}

def write(tmp_path, rows):
    p = tmp_path / ".codex/session.jsonl"
    p.parent.mkdir(exist_ok=True)
    p.write_text("\n".join(json.dumps(x) for x in rows))
    return p

def test_message_only_and_noise(tmp_path):
    p = write(tmp_path, [message("# AGENTS.md instructions injected"), message("trend-radar 확인해줘"),
                        {"type": "turn_context", "payload": {"cwd": str(tmp_path)}}])
    turns = list(tt._codex_turns(p))
    assert len(turns) == 1 and turns[0]["cwd"] == str(tmp_path)

def test_dual_records_dedup_and_repeated_input(tmp_path):
    p = write(tmp_path, [message("계속"), event("계속"),
        {"type": "response_item", "payload": {"type": "function_call", "arguments": "read file"}},
        message("계속"), event("계속")])
    turns = list(tt._codex_turns(p))
    assert len(turns) == 2 and turns[0]["tool_text"] == ["read file"]

def test_legacy_event_only(tmp_path):
    assert len(list(tt._codex_turns(write(tmp_path, [event("확인해줘")])))) == 1

def test_continuation_to_contract(tmp_path, monkeypatch):
    target = tmp_path / "radar"
    target.mkdir()
    transcript = write(tmp_path, [message("trend-radar 확인해줘"),
        {"type": "response_item", "payload": {"type": "function_call",
            "arguments": json.dumps({"workdir": str(target), "cmd": "rg 실패"})}}, message("이어서")])
    monkeypatch.setattr(ug, "_tag_targets", lambda: tt)
    monkeypatch.setattr(tt, "project_roots", lambda _: [(str(target), "trend-radar")])
    monkeypatch.setattr(tt, "submodule_dirs", lambda _: [])
    monkeypatch.setattr(ug, "load_projects", lambda: {})
    monkeypatch.setattr(ug, "load_anchors", lambda: {})
    monkeypatch.setattr(ug, "_resolve_target", lambda *args: str(target))
    monkeypatch.setattr(ug, "do_locate", lambda _: {"status": "none", "candidates": [], "keywords": []})
    monkeypatch.setattr(ug, "_similar", lambda _: [])
    loc = ug.do_infer("이어서", str(transcript))
    assert loc["prev"] == "trend-radar" and loc["emit"]
    assert loc["emit_reason"] == "explicit_continuation"
    # Same directory also receives the start contract; it is conditional on new work.
    text = contract.format_context(loc, str(target))
    assert "work-memory" in text and "참조 ID" in text and "이미 조회" in text
    assert not ug.do_infer("흠", str(transcript))["emit"]

def test_ambiguous_does_not_start_work():
    text = contract.format_context({"status": "clarify", "emit": True,
        "candidates": [{"project": "a", "path": "/a"}, {"project": "b", "path": "/b"}]})
    assert "확인한 뒤" in text and "[uug-context]" not in text

def test_likely_requires_confirmation():
    text = contract.format_context({"status": "likely", "emit": True,
        "candidates": [{"project": "a", "path": "/a"}]})
    assert "먼저 확인" in text

def test_event_first_dedup_preserves_ref(tmp_path):
    e = event("계속")
    e["payload"]["item"]["id"] = "stable-event-id"
    turns = list(tt._codex_turns(write(tmp_path, [e, message("계속")])))
    assert len(turns) == 1 and turns[0]["ref"] == "stable-event-id"

def test_control_without_active_context(monkeypatch):
    monkeypatch.setattr(ug, "prev_target", lambda *args: None)
    monkeypatch.setattr(ug, "_similar", lambda _: [])
    loc = ug.do_infer("계속")
    assert not loc["emit"] and contract.format_context(loc) is None

def test_explicit_project_switch_wins(monkeypatch):
    monkeypatch.setattr(ug, "prev_target", lambda *args: "content-broadcast-hub")
    monkeypatch.setattr(ug, "do_locate", lambda _: {"status": "clear", "emit": False,
        "candidates": [{"project": "trend-radar", "path": "/radar"}], "keywords": ["trend-radar"]})
    loc = ug.do_infer("trend-radar 확인해줘")
    assert loc["emit"] and loc["candidates"][0]["project"] == "trend-radar"

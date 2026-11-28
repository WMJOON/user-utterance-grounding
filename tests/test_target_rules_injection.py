"""uug-locate 가 작업 대상으로 이동할 때 대상 저장소 CLAUDE.md 를 주입하는지 검증."""
import importlib.util
from pathlib import Path

HOOK = Path(__file__).resolve().parents[1] / "skills" / "uug-grounding" / "hooks" / "context_contract.py"


def _load(tmp_path, monkeypatch, **env):
    monkeypatch.setenv("UUG_TARGET_RULES_STATE", str(tmp_path / "state.json"))
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    spec = importlib.util.spec_from_file_location("cc", HOOK)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _loc(path, status="confirmed"):
    return {"emit": True, "status": status, "candidates": [{"project": "t", "path": str(path)}]}


def test_injects_target_claude_md(tmp_path, monkeypatch):
    target = tmp_path / "repo"; target.mkdir()
    (target / "CLAUDE.md").write_text("엠대시 금지", encoding="utf-8")
    m = _load(tmp_path, monkeypatch)
    out = m.format_context(_loc(target), cwd=str(tmp_path / "other"))
    assert "[uug-target-rules]" in out and "엠대시 금지" in out


def test_skips_when_already_in_target(tmp_path, monkeypatch):
    target = tmp_path / "repo"; target.mkdir()
    (target / "CLAUDE.md").write_text("x", encoding="utf-8")
    m = _load(tmp_path, monkeypatch)
    assert "[uug-target-rules]" not in m.format_context(_loc(target), cwd=str(target))


def test_dedupes_within_ttl(tmp_path, monkeypatch):
    target = tmp_path / "repo"; target.mkdir()
    (target / "CLAUDE.md").write_text("x", encoding="utf-8")
    m = _load(tmp_path, monkeypatch)
    first = m.format_context(_loc(target), cwd="/elsewhere")
    second = m.format_context(_loc(target), cwd="/elsewhere")
    assert "[uug-target-rules]" in first and "[uug-target-rules]" not in second


def test_reinjects_when_rules_change(tmp_path, monkeypatch):
    target = tmp_path / "repo"; target.mkdir()
    f = target / "CLAUDE.md"; f.write_text("v1", encoding="utf-8")
    m = _load(tmp_path, monkeypatch)
    m.format_context(_loc(target), cwd="/elsewhere")
    f.write_text("v2", encoding="utf-8")
    assert "v2" in m.format_context(_loc(target), cwd="/elsewhere")


def test_truncates_long_rules(tmp_path, monkeypatch):
    target = tmp_path / "repo"; target.mkdir()
    (target / "CLAUDE.md").write_text("가" * 500, encoding="utf-8")
    m = _load(tmp_path, monkeypatch, UUG_TARGET_RULES_MAX_CHARS="100")
    out = m.format_context(_loc(target), cwd="/elsewhere")
    assert "이하 생략" in out and "가" * 101 not in out


def test_no_injection_for_likely_or_clarify(tmp_path, monkeypatch):
    target = tmp_path / "repo"; target.mkdir()
    (target / "CLAUDE.md").write_text("x", encoding="utf-8")
    m = _load(tmp_path, monkeypatch)
    assert "[uug-target-rules]" not in m.format_context(_loc(target, "likely"), cwd="/elsewhere")
    assert "[uug-target-rules]" not in m.format_context(_loc(target, "clarify"), cwd="/elsewhere")


def test_falls_back_to_agents_md(tmp_path, monkeypatch):
    target = tmp_path / "repo"; target.mkdir()
    (target / "AGENTS.md").write_text("agents rule", encoding="utf-8")
    m = _load(tmp_path, monkeypatch)
    assert "agents rule" in m.format_context(_loc(target), cwd="/elsewhere")

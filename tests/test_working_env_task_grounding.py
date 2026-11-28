"""working-environment 슬롯(맥락) + repository task grounding.

repository lexical 로 대상이 확정되면 슬롯이 전환되고, 이후 task lexical 은 슬롯 저장소의 절차로 해석된다.
"""
import importlib.util
from pathlib import Path

HOOK = Path(__file__).resolve().parents[1] / "skills" / "uug-grounding" / "hooks" / "context_contract.py"

PROJECTS = {
    "content-broadcast-hub": {"tasks": [
        {"id": "notion-register", "lexical": ["노션에 올려", "노션 업로드"], "procedure": "complete_content.py"},
        {"id": "content-write", "lexical": ["콘텐츠로 만들"], "procedure": "content/in-process/main.md"},
    ]},
    "family-wealth": {"tasks": []},
    "visual-identity-ontology": {"tasks": [
        {"id": "image-upload", "lexical": ["이미지 노션"], "procedure": "vio upload"},
    ]},
}


def _load(tmp_path, monkeypatch):
    monkeypatch.setenv("UUG_WORKING_ENV_STATE", str(tmp_path / "env.json"))
    monkeypatch.setenv("UUG_TARGET_RULES_STATE", str(tmp_path / "rules.json"))
    spec = importlib.util.spec_from_file_location("cc", HOOK)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _clear(repo):
    return {"status": "clear", "emit": True, "candidates": [{"project": repo, "path": f"/x/{repo}"}]}


def test_repository_trigger_switches_working_env(tmp_path, monkeypatch):
    m = _load(tmp_path, monkeypatch)
    key = m.session_key("t1")
    assert m.update_working_env(_clear("content-broadcast-hub"), key)["repo"] == "content-broadcast-hub"
    assert m.working_env(key)["by"] == "repository_trigger"


def test_non_clear_does_not_switch(tmp_path, monkeypatch):
    m = _load(tmp_path, monkeypatch)
    key = m.session_key("t1")
    m.update_working_env(_clear("family-wealth"), key)
    m.update_working_env({"status": "inferred", "emit": True,
                          "candidates": [{"project": "content-broadcast-hub"}]}, key)
    m.update_working_env({"status": "likely", "emit": True,
                          "candidates": [{"project": "content-broadcast-hub"}]}, key)
    assert m.working_env(key)["repo"] == "family-wealth"


def test_task_lexical_grounds_to_env_repository_task(tmp_path, monkeypatch):
    m = _load(tmp_path, monkeypatch)
    key = m.session_key("t1")
    m.update_working_env(_clear("content-broadcast-hub"), key)
    res = m.ground_task("노션에 올려줘", m.working_env(key), PROJECTS)
    assert res[0] == "grounded" and res[2][0]["id"] == "notion-register"
    assert "complete_content.py" in m.format_task(res, m.working_env(key))


def test_task_lexical_outside_env_suggests_switch(tmp_path, monkeypatch):
    m = _load(tmp_path, monkeypatch)
    key = m.session_key("t1")
    m.update_working_env(_clear("family-wealth"), key)
    res = m.ground_task("오늘 작업건 콘텐츠로 만들어줘", m.working_env(key), PROJECTS)
    assert res[0] == "switch" and res[1] == "content-broadcast-hub"
    assert "전환할지" in m.format_task(res, m.working_env(key))


def test_no_task_no_message(tmp_path, monkeypatch):
    m = _load(tmp_path, monkeypatch)
    assert m.ground_task("테스트 돌려줘", {"repo": "content-broadcast-hub"}, PROJECTS) is None


def test_sessions_are_isolated(tmp_path, monkeypatch):
    m = _load(tmp_path, monkeypatch)
    m.update_working_env(_clear("content-broadcast-hub"), m.session_key("a"))
    assert m.working_env(m.session_key("b")) is None

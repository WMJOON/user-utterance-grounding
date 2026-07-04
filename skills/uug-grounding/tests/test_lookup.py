"""user-utterance-grounding lookup 테스트. 실행: python3 -m pytest tests/ (rdflib 필요)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
import lookup  # noqa: E402

EXPECTED_INTENTS = {"work-on-project", "add-to-knowledge", "run-research", "record-memory", "tidy-organize"}


def test_list_intents_loads_ttl():
    ids = {i["intent_id"] for i in lookup.list_intents()}
    assert ids == EXPECTED_INTENTS


def test_every_intent_has_target_project_slot():
    for intent in lookup.list_intents():
        names = {s["slot_name"] for s in intent["slot_specs"]}
        assert "target_project" in names, f"{intent['intent_id']} missing target_project slot"


def test_every_user_intent_declares_scope():
    """UD-0001: user 레지스트리 intent 는 전부 scope 를 선언한다."""
    valid = {"meta", "repository", "workflow", "workflow.executionRail"}
    by_id = {i["intent_id"]: i["scope"] for i in lookup.list_intents()}
    assert set(by_id.values()) <= valid, by_id
    assert by_id["record-memory"] == "meta"          # dialog/컨텍스트 무관 기록
    assert by_id["work-on-project"] == "repository"
    assert by_id["tidy-organize"] == "repository"


def test_match_intent_basic():
    assert lookup.match_intent("이 개념 KB에 추가해줘")["intent"]["intent_id"] == "add-to-knowledge"
    assert lookup.match_intent("이거 착수하자")["intent"]["intent_id"] == "work-on-project"
    assert lookup.match_intent("정리하자")["intent"]["intent_id"] == "tidy-organize"


def test_match_intent_no_match():
    m = lookup.match_intent("점심 뭐먹지")
    assert m["intent"] is None
    assert m["top2_score"] is None and m["margin"] is None


def test_match_intent_margin_solo():
    """후보 1개 → 경쟁 없음: margin None."""
    m = lookup.match_intent("착수하자")
    assert m["intent"]["intent_id"] == "work-on-project"
    assert m["top2_score"] is None and m["margin"] is None
    assert m["ambiguous"] is False


def test_match_intent_margin_tie():
    """동점(정리=tidy 1 vs 기록=record 1) → margin 0 = ambiguous."""
    m = lookup.match_intent("정리 기록")
    assert m["margin"] == 0 and m["top2_score"] == m["score"]
    assert m["ambiguous"] is True


def test_match_intent_margin_one():
    """근소 우세(tidy 2 hits vs record 1 hit) → margin 1, ambiguous 아님."""
    m = lookup.match_intent("기록 정리하자")
    assert m["intent"]["intent_id"] == "tidy-organize"
    assert m["score"] == 2 and m["top2_score"] == 1 and m["margin"] == 1
    assert m["ambiguous"] is False


def test_add_to_knowledge_target_default():
    intent = lookup.lookup_intent("add-to-knowledge")
    tp = next(s for s in intent["slot_specs"] if s["slot_name"] == "target_project")
    assert tp["fill_policy"] == "default"
    assert tp["default_value"] == "agent-knowledge-base"

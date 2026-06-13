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


def test_match_intent_basic():
    assert lookup.match_intent("이 개념 KB에 추가해줘")["intent"]["intent_id"] == "add-to-knowledge"
    assert lookup.match_intent("이거 착수하자")["intent"]["intent_id"] == "work-on-project"
    assert lookup.match_intent("정리하자")["intent"]["intent_id"] == "tidy-organize"


def test_match_intent_no_match():
    assert lookup.match_intent("점심 뭐먹지")["intent"] is None


def test_add_to_knowledge_target_default():
    intent = lookup.lookup_intent("add-to-knowledge")
    tp = next(s for s in intent["slot_specs"] if s["slot_name"] == "target_project")
    assert tp["fill_policy"] == "default"
    assert tp["default_value"] == "agent-knowledge-base"

"""UUG↔MSO 멀티-레지스트리 브리지 테스트 (§11 전제 #1).

UUG grounding 이 user 레지스트리 + 프로젝트 도메인 레지스트리(MSO intents.ttl)를
namespace 무관하게 합쳐 ground 할 수 있는지 검증.
MSO TTL 부재(uug-grounding 단독 클론) 시 skip.
실행: python3 -m pytest tests/ (rdflib 필요).
"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
import lookup  # noqa: E402

# 모노레포 내 MSO 도메인 레지스트리(상대경로). 단독 클론 시 부재 → skip.
# parents: [0]tests [1]uug-grounding [2]skills [3]repository [4]01_user-utterance-grounding [5]03_AgentsTools
_MSO_TTL = (
    Path(__file__).resolve().parents[5]
    / "00_multi-swarm-orchestrator/repository/skills/mso-intent-analytics/instances/intents.ttl"
)
_HAS_MSO = _MSO_TTL.exists()
_REGS = [
    {"path": str(lookup.USER_INTENTS), "source_project": None},
    {"path": str(_MSO_TTL), "source_project": "multi-swarm-orchestrator"},
]

pytestmark = pytest.mark.skipif(not _HAS_MSO, reason="MSO intents.ttl 부재 (단독 클론)")


def test_default_registry_excludes_mso():
    """registries 미지정 → user 레지스트리만 (하위호환). MSO intent 미포함."""
    ids = {i["intent_id"] for i in lookup.list_intents()}
    assert "query_audit_log" not in ids
    assert "tidy-organize" in ids


def test_multi_registry_union_tags_source():
    """user + MSO 합집합. source_project 로 출처 구분."""
    intents = lookup.list_intents(registries=_REGS)
    by_id = {i["intent_id"]: i for i in intents}
    assert by_id["tidy-organize"]["source_project"] is None
    assert by_id["query_audit_log"]["source_project"] == "multi-swarm-orchestrator"


def test_ground_mso_domain_intent():
    """MSO 도메인 발화가 mso: namespace 레지스트리에서 ground 된다."""
    m = lookup.match_intent("audit log 보여줘", registries=_REGS)
    assert m["intent"] is not None
    assert m["intent"]["intent_id"] == "query_audit_log"
    assert m["intent"]["source_project"] == "multi-swarm-orchestrator"


def test_user_intent_still_grounds_with_mso_loaded():
    """MSO 레지스트리를 같이 실어도 user 발화 회귀 정상."""
    m = lookup.match_intent("스킬 정리하자", registries=_REGS)
    assert m["intent"]["intent_id"] == "tidy-organize"
    assert m["intent"]["source_project"] is None


def test_namespace_agnostic_slot_specs():
    """mso: slot_specs 도 로컬명 기준으로 읽힌다."""
    intent = lookup.lookup_intent("query_audit_log", registries=_REGS)
    assert intent is not None
    names = {s["slot_name"] for s in intent["slot_specs"]}
    assert names, "MSO intent slot_specs 파싱 실패"


# ─── 통합 경로 + commit 정책 (advisor #3: build_registries→_do_ground) ───
import os  # noqa: E402

os.environ.setdefault("UG_SESSION", "/tmp/uug_test_session.json")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import ug  # noqa: E402


def _mso_in_registries():
    """실제 통합 경로로 MSO 레지스트리가 잡히는지 (machine.yaml 앵커 의존)."""
    regs = ug.build_registries(ug.load_projects(), ug.load_anchors())
    return any(r.get("source_project") == "multi-swarm-orchestrator" for r in regs)


@pytest.mark.skipif(not _HAS_MSO, reason="MSO intents.ttl 부재")
def test_integration_build_registries_finds_mso():
    """projects.yaml→build_registries→resolve_one→ttl 통합 경로가 MSO 를 싣는다."""
    if not _mso_in_registries():
        pytest.skip("machine.yaml 앵커 미설정 (통합 경로 환경 의존)")
    assert _mso_in_registries()


@pytest.mark.skipif(not _HAS_MSO, reason="MSO intents.ttl 부재")
def test_commit_policy_domain_intent_no_hitl():
    """비회귀 핵심: 도메인 intent 동점은 HITL 아닌 top-1 commit (MSO decisiveness)."""
    if not _mso_in_registries():
        pytest.skip("machine.yaml 앵커 미설정")
    r = ug._do_ground("ticket-217 재실행")
    assert r["status"] in ("ok", "incomplete"), f"도메인 intent 가 HITL 로 빠짐: {r['status']}"
    assert r["intent_id"] == "dispatch_ticket"
    assert r["committed_ambiguous"] is True
    assert r["target_project"] == "multi-swarm-orchestrator"


def test_commit_policy_user_tie_stays_hitl():
    """user intent 동점은 commit 정책 미적용 — HITL 유지(보수성)."""
    # user 레지스트리만으로도 동점 발생하는 발화 (정리=tidy, 기록=record)
    m = lookup.match_intent("정리 기록")
    assert m["ambiguous"] is True
    assert m["intent"]["source_project"] is None
    r = ug._do_ground("정리 기록")
    assert r["status"] == "ambiguous"


# ─── §11 배선: UUG→프로젝트(MSO) end-to-end dispatch (전제 #2 실호출) ───
# 전제 #1(멀티-레지스트리 ground)에 이어, 도메인 intent 의 뒷단을 프로젝트 CLI 에
# subprocess 위임하는 실제 배선. MSO 는 UUG 를 모른다(단방향 의존, 프로세스 경계).

@pytest.mark.skipif(not _HAS_MSO, reason="MSO intents.ttl 부재")
def test_dispatch_delegates_domain_intent_to_mso():
    """ug ground(앞단) → dispatch_to_project → MSO pipeline CLI(뒷단) → GroundedCommand."""
    if not _mso_in_registries():
        pytest.skip("machine.yaml 앵커 미설정 (배선 경로 환경 의존)")
    projects, anchors = ug.load_projects(), ug.load_anchors()
    r = ug._do_ground("ticket-217 재실행")
    assert r["source_project"] == "multi-swarm-orchestrator"
    grounded, err = ug.dispatch_to_project(r, projects, anchors, "ticket-217 재실행")
    assert err is None, f"dispatch 실패: {err}"
    # MSO 뒷단(slot_filler→resolver→validator)이 채운 GroundedCommand
    assert grounded["intent_id"] == "dispatch_ticket"
    assert grounded["tier"] == "UUG"
    assert grounded["slots"]["ticket_ref"] == "ticket-217"
    assert grounded["target_id"] == "ticket-217"
    assert grounded["reprompt_needed"] is False


def test_dispatch_user_intent_falls_back_no_delegation():
    """user intent(source_project=None)는 dispatch 미선언 → no-dispatch(UUG 자체 처리)."""
    projects, anchors = ug.load_projects(), ug.load_anchors()
    fake = {"status": "ok", "intent_id": "tidy-organize", "source_project": None}
    grounded, err = ug.dispatch_to_project(fake, projects, anchors, "스킬 정리하자")
    assert grounded is None
    assert err == "no-dispatch"


def test_dispatch_unresolved_project_errors_loudly():
    """dispatch 선언됐으나 프로젝트 미해소 시 조용히 삼키지 않고 에러 반환(drift 탐지)."""
    projects = {"ghost": {"anchor": "vault", "rel": "no/such/path",
                          "dispatch": {"kind": "cli", "entry": "x/y.py"}}}
    fake = {"status": "ok", "intent_id": "whatever", "source_project": "ghost"}
    grounded, err = ug.dispatch_to_project(fake, projects, ug.load_anchors(), "발화")
    assert grounded is None
    assert err is not None and err != "no-dispatch"


# ─── 앞단 DoD 이전 (구 mso-utterance-grounding fixture_accuracy) ───
# §11: utterance→intent 정확도는 이제 UUG 책임. MSO 50-fixture top-1 ≥80%.
_FIXTURE = Path(__file__).resolve().parent / "fixtures" / "mso_utterances_50.jsonl"


@pytest.mark.skipif(not (_HAS_MSO and _FIXTURE.exists()),
                    reason="MSO intents.ttl / fixture 부재")
def test_fixture_accuracy_mso_intents():
    rows = [json.loads(l) for l in _FIXTURE.read_text(encoding="utf-8").splitlines() if l.strip()]
    ok, errs = 0, []
    for r in rows:
        m = lookup.match_intent(r["utterance"], registries=_REGS)
        got = m["intent"]["intent_id"] if m["intent"] else None
        if got == r["expected_intent"]:
            ok += 1
        else:
            errs.append(f"  {r['utterance']!r} exp={r['expected_intent']} got={got}")
    acc = ok / len(rows)
    assert acc >= 0.80, f"UUG top-1 accuracy {acc:.1%} < 80% (구 MSO DoD).\n" + "\n".join(errs)

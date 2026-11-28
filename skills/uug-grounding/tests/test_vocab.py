"""작업어휘·지시문 SKOS + Binary Condition (UD-0004) 테스트.

C1 작업어휘는 프로젝트 지칭어가 아니다 / C2 지시문 서법 / C3 직전 레포 적용 빈도.
실제 사용자 데이터(projects.yaml·빈도 맵)에 기대지 않도록 가짜 레지스트리·맵으로 격리한다.
"""
import json
import sys
from pathlib import Path

import pytest

SKILL = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL / "src"))
sys.path.insert(0, str(SKILL / "scripts"))

import lookup  # noqa: E402
import ug  # noqa: E402
import vocab  # noqa: E402


# ─── 스킴 무결성 ───
def test_vocab_conforms_to_shacl():
    pyshacl = pytest.importorskip("pyshacl")
    from rdflib import Graph
    data = Graph().parse(str(vocab.VOCAB_TTL))
    shapes = Graph().parse(str(SKILL / "references" / "shapes" / "vocab_shapes.ttl"))
    assert pyshacl.validate(data, shacl_graph=shapes)[0]


def test_missing_facet_violates_shacl():
    """facet 하나라도 빠지면 '모름'이 되어 binary 가 깨진다 → 위반이어야 한다."""
    pyshacl = pytest.importorskip("pyshacl")
    from rdflib import Graph
    ttl = vocab.VOCAB_TTL.read_text(encoding="utf-8")
    broken = ttl.replace("uug:isWorkflow true ; uug:isRepository false ; uug:isExecution false ; uug:isArtifact false .",
                         "uug:isWorkflow true ; uug:isRepository false ; uug:isExecution false .", 1)
    assert broken != ttl
    shapes = Graph().parse(str(SKILL / "references" / "shapes" / "vocab_shapes.ttl"))
    assert not pyshacl.validate(Graph().parse(data=broken, format="turtle"), shacl_graph=shapes)[0]


def test_every_work_term_has_four_booleans():
    for c in vocab.list_concepts("WorkTermScheme"):
        assert set(c["facets"]) == set(vocab.FACETS)
        assert all(isinstance(v, bool) for v in c["facets"].values()), c["concept"]


# ─── C1 작업어휘 / facet ───
def test_match_terms_and_facets():
    terms = vocab.match_terms("이 레포 리서치 해줘")
    assert {t["concept"] for t in terms} == {"RepositoryWord", "Research"}
    f = vocab.facet_vector("이 레포 리서치 해줘", terms)
    assert f["isRepository"] and f["isWorkflow"] and f["isArtifact"] and not f["isExecution"]


def test_facet_vector_unknown_without_terms():
    """작업어휘가 없으면 발화 facet 은 False 가 아니라 None(모름)."""
    assert all(v is None for v in vocab.facet_vector("음 그렇구나").values())


def test_ascii_label_needs_word_boundary():
    assert not vocab.match_terms("reposition the box")
    assert {t["concept"] for t in vocab.match_terms("check the repo")} == {"RepositoryWord"}


# ─── C2 지시문 ───
@pytest.mark.parametrize("utt,expected", [
    ("리서치 해줘", True), ("정리하자", True), ("wf-001 계속해", True),
    ("리서치 어때?", False), ("이거 정리할까", True), ("이거 맞아?", False),
    ("evidence로 구조화해볼까?", True), ("1번", True), ("세션 이전 레포와 같으면 생략해도 되는 거지", False),
    ("kb에 리서치좀 해보자고", True), ("이게 맞나", False),
    ("리서치", None),
])
def test_is_command(utt, expected):
    assert vocab.is_command(utt) is expected


# ─── 동점 해소 (lookup) ───
def test_tie_without_external_evidence_stays_ambiguous():
    """'정리 기록' — 각 intent 의 facet 근거가 자기 트리거뿐이면(순환) 해소하지 않는다."""
    m = lookup.match_intent("정리 기록")
    assert m["margin"] == 0 and m["ambiguous"] is True
    assert m["tiebreak"]["resolved"] is False


def test_tie_resolved_by_other_term_facet():
    """'레포 정리 기록' — 트리거 밖의 '레포'(isRepository)가 repository scope 인 tidy 를 지지."""
    m = lookup.match_intent("레포 정리 기록")
    assert m["margin"] == 0
    assert m["tiebreak"]["resolved"] is True
    assert m["intent"]["intent_id"] == "tidy-organize"
    assert m["ambiguous"] is False


def test_vocab_labels_union_into_triggers():
    intent = lookup.lookup_intent("run-research")
    assert "Research" in intent["vocab_concepts"]
    for kw in ("리서치", "자료 조사", "조사해줘"):   # 기존 키워드 보존 + 어휘 label
        assert kw in intent["trigger_keywords"]


# ─── C1 locate: 작업어휘는 explicit 지칭이 아니다 ───
@pytest.fixture
def fake_registry(monkeypatch, tmp_path):
    projects = {
        "kb":  {"anchor": "vault", "rel": "kb", "keywords": ["리서치"]},
        "hub": {"anchor": "vault", "rel": "hub", "keywords": ["콘텐츠 허브"]},   # :Keyword (alias 아님)
    }
    monkeypatch.setattr(ug, "load_projects", lambda: projects)
    monkeypatch.setattr(ug, "present_projects", lambda p, a: p)  # 가짜 경로 — 기기 존재 필터 우회
    monkeypatch.setattr(ug, "_umbrella_subs", lambda p, a: {"repository": "umbrella:sub/repository"})
    monkeypatch.setattr(ug, "KEYWORD_MAP", tmp_path / "no-keyword-map.json")
    vmap = {"_meta": {"utterances": 150, "project_n": {"kb": 50, "hub": 100}},
            "Research": {"n": 20, "candidates": [
                {"project": "kb", "count": 18, "share": 0.9},
                {"project": "hub", "count": 1, "share": 0.05}]},
            "ExecutionWord": {"n": 30, "candidates": [
                {"project": "hub", "count": 10, "share": 0.33},
                {"project": "kb", "count": 9, "share": 0.3}]}}
    p = tmp_path / "vocab-term-map.json"
    p.write_text(json.dumps(vmap), encoding="utf-8")
    monkeypatch.setattr(ug, "VOCAB_MAP", p)
    monkeypatch.setattr(ug, "_similar", lambda *a, **k: [])
    return projects


def test_submodule_dirname_matching_vocab_is_not_explicit(fake_registry):
    """2026-11-25 사고: 'repository' 가 서브모듈 디렉토리명으로 explicit clear 확정됐다."""
    loc = ug.do_locate("Workflow Repository Execution Artifact 를 바이너리로 만들면 어떨까")
    assert loc["status"] == "none"


def test_registered_project_id_still_explicit(fake_registry):
    assert ug.do_locate("hub 에서 정리해줘")["status"] == "clear"


# ─── C3 직전 레포 적용 빈도 ───
def test_c3_low_rate_in_prev_redirects(fake_registry):
    vr = ug.vocab_redirect("리서치 해줘", "hub")
    assert vr["c3"] is False and vr["project"] == "kb"


def test_c3_true_when_prev_uses_term(fake_registry):
    assert ug.vocab_redirect("리서치 해줘", "kb")["c3"] is True


def test_c3_unknown_for_diffuse_term(fake_registry):
    """여러 레포에 퍼진 일반 어휘(점유 < 50%)는 어느 레포의 업무라 말할 수 없다."""
    assert ug.vocab_redirect("이거 실행해줘", "hub")["c3"] is None


def test_c3_unknown_when_prev_sparse(fake_registry, monkeypatch):
    assert ug.vocab_redirect("리서치 해줘", "ghost")["c3"] is None


def test_infer_likely_recommends_topic_over_continuity(fake_registry, monkeypatch):
    """tacit '리서치'→kb, 직전 hub. hub 에선 드문 업무라 연속성 대신 kb 를 추천(되묻기 유지)."""
    monkeypatch.setattr(ug, "prev_target", lambda t, u="": "hub")
    r = ug.do_infer("리서치 해줘")
    assert r["status"] == "clarify" and r["emit"] is True
    assert r["recommended"] == "kb" and r["recommended_by"] == "작업어휘 빈도"


def test_infer_none_keyword_redirects_by_vocab(fake_registry, monkeypatch):
    """프로젝트 키워드 없는 발화('자료 조사')도 직전 레포에서 드문 업무면 추천을 돌린다."""
    monkeypatch.setattr(ug, "prev_target", lambda t, u="": "hub")
    r = ug.do_infer("자료 조사 좀 해줘")
    assert r["status"] == "clarify"
    assert [c["project"] for c in r["candidates"]] == ["kb", "hub"]
    assert r["recommended"] == "kb"


def test_infer_keeps_continuity_when_prev_applies(fake_registry, monkeypatch):
    """작업어휘가 가리키는 레포 == 직전 레포 → 되묻지 않고 그대로 추정."""
    monkeypatch.setattr(ug, "prev_target", lambda t, u="": "kb")
    r = ug.do_infer("자료 조사 좀 해줘")
    assert r["status"] == "likely" and r["candidates"][0]["project"] == "kb"


# ─── UD-0006: :ProjectName > :WorkTerm > :Keyword > :Directive ───
def test_workterm_points_to_repo(fake_registry):
    """v0.5.0 회귀: 작업어휘가 레포를 전혀 가리키지 못했다. 이제 학습 빈도로 추정한다."""
    loc = ug.do_locate("리서치 해줘")
    assert loc["status"] == "likely"
    c = loc["candidates"][0]
    assert c["project"] == "kb" and c["kind"] == "workterm" and c["share"] == 0.9


def test_workterm_without_project_keyword_still_points(fake_registry):
    """'자료 조사'는 projects.yaml 키워드가 아니지만 작업어휘(Research)라 레포를 가리킨다."""
    loc = ug.do_locate("자료 조사 좀 해줘")
    assert loc["status"] == "likely" and loc["candidates"][0]["project"] == "kb"


def test_project_name_beats_workterm(fake_registry):
    loc = ug.do_locate("hub 에서 리서치 해줘")
    assert loc["status"] == "clear" and loc["candidates"][0]["project"] == "hub"


def test_workterm_beats_keyword(fake_registry):
    """작업어휘(→kb)와 주제어(→hub)가 갈리면 되묻되 작업어휘 쪽을 추천."""
    loc = ug.do_locate("콘텐츠 허브 관련 리서치 해줘")
    assert loc["status"] == "clarify"
    assert loc["recommended"] == "kb" and loc["recommended_by"] == "작업어휘"
    assert [c["project"] for c in loc["candidates"]] == ["kb", "hub"]


def test_diffuse_workterm_gives_no_repo(fake_registry):
    """여러 레포에 퍼진 작업어휘(점유 < 50%)는 레포 신호가 아니다."""
    assert ug.do_locate("이거 실행해줘")["status"] == "none"


def test_directive_alone_gives_no_repo(fake_registry):
    assert ug.do_locate("좋아 해줘")["status"] == "none"


def test_workterm_falls_back_to_keyword_without_map(fake_registry, monkeypatch, tmp_path):
    """빈도 맵이 없으면 projects.yaml 키워드(:Keyword) 판정으로 폴백 — v0.4.0 동작."""
    monkeypatch.setattr(ug, "VOCAB_MAP", tmp_path / "missing.json")
    loc = ug.do_locate("리서치 해줘")
    assert loc["status"] == "likely"
    assert loc["candidates"][0]["project"] == "kb" and loc["candidates"][0]["kind"] == "tacit"


def test_workterm_never_explicit(fake_registry):
    """작업어휘는 확정 지칭어가 아니다 — 'repository' 서브모듈명은 빈도 맵이 없어도 무시."""
    loc = ug.do_locate("repository 정리 방식을 바꾸자")
    assert loc["status"] != "clear"


# ─── '정리' 동음이의어 (2026-11-25 발화 분석) ───
@pytest.mark.parametrize("utt,expected", [
    ("엉뚱한 bot들은 다 정리하자", {"Tidy"}),
    ("주요 개념을 skos로 정리해줘", {"Structure"}),
    ("워크트리 정리하자", {"Tidy"}),
])
def test_organize_homonym_split(utt, expected):
    assert {t["concept"] for t in vocab.match_terms(utt)} == expected

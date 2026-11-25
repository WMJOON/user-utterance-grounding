"""user-utterance-grounding — 작업어휘·지시문 SKOS 소비 API (UD-0004).

SoT = taxonomy/vocab_terms.ttl.
RDFLib 로 읽는다 (프로젝트 지침: lookup.py 와 같은 RDFLib 경로, mtime 캐시).

Binary Condition (발화 단위):
  C1 has_work_term   — 작업어휘가 있는가. 있으면 그 label 은 프로젝트 지칭어가 아니다.
  C2 is_command      — 발화 끝 지시문이 실행 요청(명령·청유)인가. 판정 불가면 None.
  C3 prev_applies    — 그 작업어휘가 직전 작업 레포에서 충분히 쓰였는가 (빈도 맵 기반, ug.py).
facet(개념 단위)은 정확히 하나의 boolean 이다. 발화 단위 facet 은 매칭된 개념들의 OR 이고,
작업어휘가 하나도 없으면 None(모름) — 개념 단위 binary 와 구분한다.
"""
from __future__ import annotations

import re
from pathlib import Path

from rdflib import Graph, Literal, Namespace
from rdflib.namespace import SKOS

_SKILL_DIR = Path(__file__).resolve().parent.parent
VOCAB_TTL = _SKILL_DIR / "taxonomy" / "vocab_terms.ttl"
UUG = Namespace("https://uug.dev/ontology/")

FACETS = ("isWorkflow", "isRepository", "isExecution", "isArtifact")
# UD-0001 scope → facet. meta 는 scope 무관이라 대응 facet 이 없다.
SCOPE_FACET = {"repository": "isRepository", "workflow": "isWorkflow",
               "workflow.executionRail": "isExecution"}

_cache: dict[str, tuple] = {}


def _graph() -> Graph:
    """vocab TTL. mtime 이 바뀌면 재로드. 파일이 없으면 빈 어휘(기존 키워드 동작 그대로)."""
    key = (str(VOCAB_TTL), VOCAB_TTL.stat().st_mtime) if VOCAB_TTL.exists() else None
    if "g" not in _cache or _cache.get("key") != key:
        g = Graph()
        if key:
            g.parse(str(VOCAB_TTL), format="turtle")
        _cache.clear()
        _cache["key"], _cache["g"] = key, g
    return _cache["g"]


def _labels(g, c) -> list[str]:
    return [str(o) for p in (SKOS.prefLabel, SKOS.altLabel) for o in g.objects(c, p)]


def _bool(g, c, name):
    v = g.value(c, UUG[name])
    return bool(v.toPython()) if isinstance(v, Literal) else None


def list_concepts(scheme: str) -> list[dict]:
    """scheme = 'WorkTermScheme' | 'DirectiveScheme'."""
    g = _graph()
    out = []
    for c in sorted(g.subjects(SKOS.inScheme, UUG[scheme])):
        d = {"concept": str(c).rsplit("/", 1)[-1], "labels": _labels(g, c)}
        if scheme == "WorkTermScheme":
            d["facets"] = {f: _bool(g, c, f) for f in FACETS}
        else:
            d["is_command"] = _bool(g, c, "isCommand")
        out.append(d)
    return out


def _hit(label: str, utt_lower: str) -> bool:
    """ug._kw_in 과 같은 규칙: 영숫자 label 은 단어 경계, 비ASCII 는 부분 문자열(조사 결합)."""
    k = label.lower()
    if not k:
        return False
    if not k.isascii():
        return k in utt_lower
    return re.search(r"(?<![A-Za-z0-9_-])" + re.escape(k) + r"(?![A-Za-z0-9_-])", utt_lower) is not None


def match_terms(utterance: str) -> list[dict]:
    """C1 — 발화에 등장한 작업어휘 개념 (hits = 맞은 label)."""
    utt = utterance.lower()
    out = []
    for c in list_concepts("WorkTermScheme"):
        hits = sorted({l for l in c["labels"] if _hit(l, utt)})
        if hits:
            out.append(dict(c, hits=hits))
    # 동음이의어 특수화: 한 개념의 hit 가 모두 다른 개념의 더 긴 hit 안에 들어가면 버린다
    # ("skos로 정리해줘" → Structure 의 "로 정리" 가 Tidy 의 "정리" 를 덮는다).
    longer = [(c["concept"], h.lower()) for c in out for h in c["hits"]]
    return [c for c in out
            if not all(any(o != c["concept"] and h.lower() != lh and h.lower() in lh
                           for o, lh in longer) for h in c["hits"])]


def term_labels() -> set[str]:
    """모든 작업어휘 label (소문자). 프로젝트 지칭어 오인 차단용."""
    return {l.lower() for c in list_concepts("WorkTermScheme") for l in c["labels"]}


def facet_vector(utterance: str, terms=None) -> dict:
    """발화 단위 facet: 매칭 개념들의 OR. 작업어휘가 없으면 전부 None(모름)."""
    terms = match_terms(utterance) if terms is None else terms
    if not terms:
        return {f: None for f in FACETS}
    return {f: any(t["facets"].get(f) for t in terms) for f in FACETS}


_TAIL = re.compile(r"[\s.!…~,]+$")


def is_command(utterance: str):
    """C2 — 발화 끝(문장부호 제외)의 가장 긴 지시문 label 로 판정.
    맞는 label 이 없으면 물음표는 False(질문), 그 외 None(판정 불가)."""
    raw = utterance.strip()
    tail = _TAIL.sub("", raw.rstrip("?？ ")).lower()
    best = None
    for c in list_concepts("DirectiveScheme"):
        for l in c["labels"]:
            if tail.endswith(l.lower()) and (best is None or len(l) > len(best[0])):
                best = (l, c["is_command"])
    if best:
        return best[1]
    return False if raw.endswith(("?", "？")) else None


def intent_compat(intent: dict, facets: dict, command) -> int:
    """동점 해소용 호환 점수 (UD-0001: hard filter 아님, 가중).
    +1 intent scope 의 facet 이 발화에서 참, +1 비명령(질문) 발화 ↔ Query verb intent."""
    score = 0
    f = SCOPE_FACET.get(intent.get("scope") or "")
    if f and facets.get(f):
        score += 1
    if command is False and intent.get("verb_concept") == "QueryVerb":
        score += 1
    return score

"""user-utterance-grounding — Lookup API (RDFLib, 서버 없음).

SoT = instances/user_intents.ttl (엄밀 TTL) + (선택) 프로젝트별 intent 레지스트리.
mso-intent-registry/src/lookup.py 의 패턴을 복사·adapt(직접 의존 X).
ug.py 의 grounding 이 match_intent() 를 호출한다.

멀티-레지스트리 브리지 (§11 전제 #1):
  user_intents.ttl(uug:) 와 프로젝트 도메인 레지스트리(예: MSO intents.ttl, mso:)는
  **술어 로컬명이 동일**(intent_id / trigger_keywords / slot_specs / slot_name …)하므로,
  이 모듈은 namespace 를 가정하지 않고 **로컬명 기준**으로 읽는다 → uug:·mso: 및 향후
  임의 프로젝트 레지스트리를 추가 코드 없이 ground 할 수 있다.
  각 intent dict 는 출처 레지스트리의 `source_project`(user 레지스트리=None)를 달고 나온다.
"""
from __future__ import annotations

from pathlib import Path

from rdflib import Graph
from rdflib.namespace import RDF

_SKILL_DIR = Path(__file__).resolve().parent.parent
# user 스코프 레지스트리(항상 로드되는 기본). ug.py 가 프로젝트 레지스트리를 덧붙인다.
USER_INTENTS = _SKILL_DIR / "instances" / "user_intents.ttl"

_graph_cache: dict[str, tuple[float, Graph]] = {}


def _load_graph(path: Path) -> Graph:
    """파일 mtime 변경 시 자동 재로드."""
    key = str(path)
    mtime = path.stat().st_mtime
    if key not in _graph_cache or _graph_cache[key][0] != mtime:
        g = Graph()
        g.parse(str(path), format="turtle")
        _graph_cache[key] = (mtime, g)
    return _graph_cache[key][1]


def _short(uri) -> str:
    if uri is None:
        return ""
    s = str(uri)
    return s.split("#")[-1].split("/")[-1] if ("#" in s or "/" in s) else s


def _rdf_list(g: Graph, head) -> list:
    """RDF list (rdf:first/rdf:rest) 순회 → 노드 목록."""
    items = []
    node = head
    while node and node != RDF.nil:
        first = g.value(node, RDF.first)
        if first is not None:
            items.append(first)
        node = g.value(node, RDF.rest)
    return items


def _props_by_localname(g: Graph, subj) -> dict[str, list]:
    """subj 의 (술어, 객체)를 술어 로컬명으로 묶는다 (namespace 무관)."""
    props: dict[str, list] = {}
    for p, o in g.predicate_objects(subj):
        props.setdefault(_short(p), []).append(o)
    return props


def _iter_intent_subjects(g: Graph):
    """rdf:type 의 로컬명이 'Intent' 인 subject (uug:Intent / mso:Intent …)."""
    for s, _, t in g.triples((None, RDF.type, None)):
        if _short(t) == "Intent":
            yield s


def _intent_to_dict(g: Graph, subj, source_project: str | None = None) -> dict:
    props = _props_by_localname(g, subj)

    def _scalar(name) -> str:
        v = props.get(name)
        return str(v[0]) if v else ""

    def _list(name) -> list[str]:
        v = props.get(name)
        return [str(x) for x in _rdf_list(g, v[0])] if v else []

    slots = []
    sslist = props.get("slot_specs")
    if sslist:
        for sn in _rdf_list(g, sslist[0]):
            sp = {_short(p): o for p, o in g.predicate_objects(sn)}
            dv = sp.get("default_value")
            slots.append({
                "slot_name":     str(sp.get("slot_name", "")),
                "slot_type":     str(sp.get("slot_type", "")),
                "required":      str(sp.get("required", "false")).lower() == "true",
                "fill_policy":   str(sp.get("fill_policy", "ask")),
                "default_value": (str(dv) if dv is not None else None),
            })

    return {
        "intent_id":        _scalar("intent_id"),
        "verb_concept":     _short(props.get("verb_concept", [None])[0]),
        "target_concept":   _short(props.get("target_concept", [None])[0]),
        "trigger_keywords": _list("trigger_keywords"),
        "slot_specs":       slots,
        "source_project":   source_project,
    }


def _normalize_registries(registries) -> list[dict]:
    """None → user 레지스트리만. dict 리스트는 {path, source_project} 로 정규화."""
    if registries is None:
        return [{"path": USER_INTENTS, "source_project": None}]
    out = []
    for r in registries:
        out.append({"path": Path(r["path"]), "source_project": r.get("source_project")})
    return out


def list_intents(registries=None) -> list[dict]:
    """등록된 모든 레지스트리의 intent 합집합.
    registries=None → user 레지스트리만 (하위호환).
    각 항목: {path, source_project}.
    """
    regs = _normalize_registries(registries)
    out, seen = [], set()
    for reg in regs:
        g = _load_graph(reg["path"])
        for subj in _iter_intent_subjects(g):
            d = _intent_to_dict(g, subj, reg["source_project"])
            key = (d["intent_id"], reg["source_project"])
            if key in seen:
                continue
            seen.add(key)
            out.append(d)
    return sorted(out, key=lambda x: (x["intent_id"], x["source_project"] or ""))


def lookup_intent(intent_id: str, registries=None) -> dict | None:
    for intent in list_intents(registries):
        if intent["intent_id"] == intent_id:
            return intent
    return None


def match_intent(utterance: str, registries=None) -> dict:
    """Lv10 rule: trigger_keywords substring 매칭으로 intent 점수화.
    registries=None → user 레지스트리만 (하위호환). 프로젝트 레지스트리를 넘기면
    그 도메인 intent(예: MSO dispatch_ticket)까지 합쳐서 점수화한다.
    Returns: {"intent": dict|None, "score": int, "hits": [...],
              "candidates": [(id, score, hits)...], "ambiguous": bool}
    """
    utt = utterance.lower()
    scored = []
    for intent in list_intents(registries):
        hits = sorted({kw for kw in intent["trigger_keywords"] if kw.lower() in utt})
        if hits:
            scored.append((len(hits), intent["intent_id"], hits, intent))
    scored.sort(key=lambda x: (-x[0], x[1]))
    if not scored:
        return {"intent": None, "score": 0, "hits": [], "candidates": [], "ambiguous": False}
    top = scored[0]
    ties = [s for s in scored if s[0] == top[0]]
    return {
        "intent": top[3],
        "score": top[0],
        "hits": top[2],
        "candidates": [(s[1], s[0], s[2]) for s in scored],
        "ambiguous": len(ties) > 1,
    }

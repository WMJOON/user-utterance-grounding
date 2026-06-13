"""user-utterance-grounding — Lookup API (RDFLib, 서버 없음).

SoT = instances/user_intents.ttl (엄밀 TTL). 이 모듈이 런타임에서 질의.
mso-intent-registry/src/lookup.py 의 패턴을 복사·adapt(직접 의존 X).
ug.py 의 grounding 이 match_intent() 를 호출한다.
"""
from __future__ import annotations

from pathlib import Path

from rdflib import Graph, Namespace
from rdflib.namespace import RDF

_SKILL_DIR = Path(__file__).resolve().parent.parent
_INSTANCES = _SKILL_DIR / "instances" / "user_intents.ttl"

UUG = Namespace("https://uug.dev/ontology/")

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


def _rdf_list(g: Graph, subj, pred) -> list:
    raw = g.value(subj, pred)
    items = []
    node = raw
    while node and node != RDF.nil:
        first = g.value(node, RDF.first)
        if first is not None:
            items.append(first)
        node = g.value(node, RDF.rest)
    return items


def _short(uri) -> str:
    if uri is None:
        return ""
    s = str(uri)
    return s.split("#")[-1].split("/")[-1] if ("#" in s or "/" in s) else s


def _intent_to_dict(g: Graph, subj) -> dict:
    slots = []
    for sn in _rdf_list(g, subj, UUG.slot_specs):
        slots.append({
            "slot_name":     str(g.value(sn, UUG.slot_name) or ""),
            "slot_type":     str(g.value(sn, UUG.slot_type) or ""),
            "required":      str(g.value(sn, UUG.required) or "false").lower() == "true",
            "fill_policy":   str(g.value(sn, UUG.fill_policy) or "ask"),
            "default_value": (str(g.value(sn, UUG.default_value)) if g.value(sn, UUG.default_value) else None),
        })
    return {
        "intent_id":        str(g.value(subj, UUG.intent_id) or ""),
        "verb_concept":     _short(g.value(subj, UUG.verb_concept)),
        "target_concept":   _short(g.value(subj, UUG.target_concept)),
        "trigger_keywords": [str(x) for x in _rdf_list(g, subj, UUG.trigger_keywords)],
        "slot_specs":       slots,
    }


def list_intents() -> list[dict]:
    g = _load_graph(_INSTANCES)
    out = [_intent_to_dict(g, s) for s in g.subjects(RDF.type, UUG.Intent)]
    return sorted(out, key=lambda x: x["intent_id"])


def lookup_intent(intent_id: str) -> dict | None:
    g = _load_graph(_INSTANCES)
    subj = UUG[intent_id]
    if (subj, RDF.type, UUG.Intent) not in g:
        return None
    return _intent_to_dict(g, subj)


def match_intent(utterance: str) -> dict:
    """Lv10 rule: trigger_keywords substring 매칭으로 intent 점수화.
    Returns: {"intent": dict|None, "score": int, "hits": [...], "candidates": [(id, score, hits)...], "ambiguous": bool}
    """
    utt = utterance.lower()
    scored = []
    for intent in list_intents():
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

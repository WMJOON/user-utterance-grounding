#!/usr/bin/env python3
"""similar.py — 과거 발화 임베딩(zvec)으로 새 발화와 비슷한 발화의 타깃 프로젝트를 찾는다.

tag_targets.py 가 타깃을 확정한 발화만 색인한다. 원문은 색인에 넣지 않는다(참조만):
벡터 + {target, source, file, ref_id} 만 저장하고, 원문은 색인 시점에 트랜스크립트에서 읽어 임베딩만 한다.

실행 환경: zvec 는 Python ≥3.10 이라 UUG 전용 venv 로 돌린다.
  ~/.local/share/uug/venv/bin/python similar.py index          # 증분 색인
  ~/.local/share/uug/venv/bin/python similar.py index --rebuild
  ~/.local/share/uug/venv/bin/python similar.py query "<발화>" [--json] [--candidates a,b]
색인은 iCloud 밖(~/.local/share/uug/zvec-utterances)에 둔다 — 머신 로컬 파생물.
"""
import argparse
import hashlib
import json
import os
import shutil
import sys
from collections import defaultdict
from pathlib import Path

os.environ.setdefault("HF_HUB_OFFLINE", "1")          # 캐시된 모델만 사용 (훅 지연·네트워크 방지)
os.environ.setdefault("TRANSFORMERS_VERBOSITY", "error")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

sys.path.insert(0, str(Path(__file__).resolve().parent))
import tag_targets  # noqa: E402  (트랜스크립트 파서·태깅 산출물 경로 재사용)

INDEX = Path(os.environ.get("UUG_ZVEC_PATH", Path.home() / ".local" / "share" / "uug" / "zvec-utterances"))
# paraphrase-multilingual-MiniLM 은 한국어 요청문("~해줘")끼리 내용과 무관하게 0.98 로 뭉쳐 부적합.
# bge-m3 는 관련 0.7 / 무관 0.45 수준으로 구분된다 (콜드 스타트 ~3.6s).
MODEL = "BAAI/bge-m3"
DIM = 1024
VEC = "dense"
TOPK = 15
MIN_SIM = 0.55   # 코사인 유사도가 이보다 낮은 이웃은 근거로 쓰지 않는다


OMLX_URL = os.environ.get("UUG_EMBED_URL", "http://localhost:1234/v1/embeddings")
OMLX_MODEL = "BAAI/bge-m3"   # ~/.omlx/model_settings.json 에 pinned(상주) 등록


def _model():
    from sentence_transformers import SentenceTransformer
    return SentenceTransformer(MODEL)


def _omlx(texts, timeout):
    import urllib.request
    import numpy as np
    out = []
    for i in range(0, len(texts), 32):
        req = urllib.request.Request(
            OMLX_URL, json.dumps({"model": OMLX_MODEL, "input": texts[i:i + 32]}).encode(),
            {"content-type": "application/json"})
        data = json.load(urllib.request.urlopen(req, timeout=timeout))["data"]
        out += [d["embedding"] for d in sorted(data, key=lambda d: d["index"])]
    v = np.array(out, dtype="float32")
    return v / np.linalg.norm(v, axis=1, keepdims=True)


def embed(texts, timeout=5):
    """omlx 상주 bge-m3(~20ms) 우선, 실패 시 로컬 sentence-transformers(콜드 ~3.6s)로 폴백."""
    try:
        return _omlx(texts, timeout)
    except Exception:
        return _model().encode(texts, batch_size=32, normalize_embeddings=True, show_progress_bar=False)


def _open(create=False):
    import zvec
    zvec.init(log_level=zvec.LogLevel.WARN)
    if create:
        schema = zvec.CollectionSchema(
            name="uug_utterances",
            fields=[zvec.FieldSchema("target", zvec.DataType.STRING),
                    zvec.FieldSchema("source", zvec.DataType.STRING, nullable=True),
                    zvec.FieldSchema("file", zvec.DataType.STRING, nullable=True),
                    zvec.FieldSchema("ref_id", zvec.DataType.STRING, nullable=True)],
            vectors=[zvec.VectorSchema(VEC, zvec.DataType.VECTOR_FP32, DIM,
                                       zvec.HnswIndexParam(metric_type=zvec.MetricType.COSINE))])
        INDEX.parent.mkdir(parents=True, exist_ok=True)
        return zvec.create_and_open(path=str(INDEX), schema=schema, option=zvec.CollectionOption())
    return zvec.open(path=str(INDEX), option=zvec.CollectionOption())


def _doc_id(file, ref):
    return hashlib.sha1(f"{file}#{ref}".encode()).hexdigest()[:24]


SEEN = INDEX.parent / "zvec-utterances.seen.json"


def cmd_index(args):
    import zvec
    if args.rebuild and INDEX.exists():
        shutil.rmtree(INDEX)
        SEEN.unlink(missing_ok=True)
    col = _open(create=not INDEX.exists())
    seen = set(json.loads(SEEN.read_text())) if SEEN.exists() else set()

    tags = {}
    for line in tag_targets.OUT.open(encoding="utf-8"):
        r = json.loads(line)
        if r.get("target"):
            tags[(r["ref"]["file"], r["ref"]["id"])] = r
    todo = []
    for turn in tag_targets.iter_turns():
        key = (turn["file"], turn["ref"])
        r = tags.get(key)
        if r and _doc_id(*key) not in seen:
            todo.append((key, r, turn["text"][:1000]))
    if not todo:
        print("[similar] 신규 0건")
        return 0

    vecs = embed([t for _, _, t in todo], timeout=120)
    docs = [zvec.Doc(id=_doc_id(*key),
                     fields={"target": r["target"], "source": r["ref"]["source"],
                             "file": key[0], "ref_id": key[1]},
                     vectors={VEC: [float(x) for x in v]})
            for (key, r, _), v in zip(todo, vecs)]
    col.upsert(docs)
    col.optimize()
    col.flush()
    seen |= {d.id for d in docs}
    SEEN.write_text(json.dumps(sorted(seen)))
    print(f"[similar] 색인 {len(docs)}건 → {INDEX} (누적 {len(seen)})")
    return 0


def _field(doc, name):
    f = getattr(doc, "fields", None)
    if isinstance(f, dict):
        return f.get(name)
    try:
        return doc.field(name)
    except Exception:
        return getattr(doc, name, None)


def query(utterance, candidates=None):
    """이웃 발화 점수를 타깃별로 합산. candidates 가 주어지면 그 안에서만 순위를 낸다."""
    import zvec
    if not INDEX.exists():
        return {"status": "no-index", "ranking": []}
    v = embed([utterance])[0]
    col = _open()
    res = col.query(queries=zvec.VectorQuery(VEC, vector=[float(x) for x in v]),
                    topk=TOPK, output_fields=None, include_vector=False)
    agg, best, n = defaultdict(float), defaultdict(float), defaultdict(int)
    for doc in res or []:
        score = 1.0 - float(getattr(doc, "score", 1) or 1)   # zvec COSINE score = 거리(1-cos)
        t = _field(doc, "target")
        if score < MIN_SIM or not t:
            continue
        if candidates and t not in candidates:
            continue
        agg[t] += score
        best[t] = max(best[t], score)
        n[t] += 1
    total = sum(agg.values()) or 1.0
    ranking = [{"project": t, "weight": round(agg[t] / total, 2), "neighbors": n[t],
                "best": round(best[t], 3)}
               for t in sorted(agg, key=lambda k: -agg[k])]
    return {"status": "ok" if ranking else "no-neighbor", "ranking": ranking}


def cmd_query(args):
    cands = [c for c in (args.candidates or "").split(",") if c] or None
    r = query(args.utterance, cands)
    if args.json:
        print(json.dumps(r, ensure_ascii=False))
        return 0
    if not r["ranking"]:
        print(f"[similar] {r['status']}")
    for x in r["ranking"]:
        print(f"  {x['project']:28} weight={x['weight']:.0%} 이웃={x['neighbors']} best={x['best']}")
    return 0


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("index"); s.add_argument("--rebuild", action="store_true")
    s.set_defaults(func=cmd_index)
    s = sub.add_parser("query"); s.add_argument("utterance")
    s.add_argument("--json", action="store_true"); s.add_argument("--candidates")
    s.set_defaults(func=cmd_query)
    args = ap.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())

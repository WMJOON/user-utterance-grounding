#!/usr/bin/env python3
"""eval_targets.py — 타깃 추론 방식 비교 실험 (leave-one-out).

정답: tag_targets.py 가 '작업 경로'로 확정한 발화 (target_via ∈ {work, utterance+work}).
방식:
  knn          bge-m3(omlx) 유사 발화 top-k 의 타깃 가중합                 (현재 locate --similar)
  prev         같은 세션 직전 발화의 타깃 (연속성)
  knn+prev     knn 점수에 직전 타깃 보너스 λ
  rerank       knn top-N 이웃을 cross-encoder(bge-reranker-v2-m3)로 재채점 후 가중합
  rerank+prev  rerank 에 직전 타깃 보너스
평가 구간: 전체 / 모호 키워드 발화(clarify 상황) / 짧은 발화(<20자)

  ~/.local/share/uug/venv/bin/python eval_targets.py [--no-rerank]
"""
import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import similar  # noqa: E402
import tag_targets  # noqa: E402

KMAP = tag_targets.SKILL_DIR / "workspace" / "keyword-map.json"
RERANKER = "BAAI/bge-reranker-v2-m3"
K, N_RERANK, MIN_SIM = 15, 30, 0.55


def load():
    tags = {}
    for line in tag_targets.OUT.open(encoding="utf-8"):
        r = json.loads(line)
        tags[(r["ref"]["file"], r["ref"]["id"])] = r
    rows = []
    for turn in tag_targets.iter_turns():
        r = tags.get((turn["file"], turn["ref"]))
        if r:
            rows.append({**r, "text": turn["text"][:1000], "file": turn["file"]})
    # 세션 내 직전 발화 타깃 (정답 여부와 무관하게 확정 타깃이 있으면 사용)
    last = {}
    for r in rows:
        r["prev"] = last.get(r["file"])
        if r["target"]:
            last[r["file"]] = r["target"]
    return rows


def knn_scores(S, i, labels, allowed=None, k=K):
    agg = defaultdict(float)
    for j in np.argsort(-S[i])[:k + 1]:
        if j == i or S[i, j] < MIN_SIM or labels[j] is None:
            continue
        if allowed and labels[j] not in allowed:
            continue
        agg[labels[j]] += float(S[i, j])
    return agg


def pick(agg, prev=None, lam=0.0, allowed=None):
    agg = dict(agg)
    if prev and lam and (not allowed or prev in allowed):
        agg[prev] = agg.get(prev, 0.0) + lam * (sum(agg.values()) or 1.0)
    return max(agg, key=agg.get) if agg else None


def gate_report(rows, S, labels, gold):
    """ug.do_infer 판정 규칙을 LOO 로 재현 → 상태별 넛지 정확도·빈도."""
    ug = tag_targets._load_ug()
    buckets = defaultdict(lambda: [0, 0])   # name → [맞음, 전체]
    for i in gold:
        g, prev = labels[i], rows[i]["prev"]
        loc = ug.do_locate(rows[i]["text"])
        names = [c["project"] for c in loc["candidates"]]
        st = loc["status"]
        if st == "clear":
            key, ok = "clear(explicit) emit", names[0] == g
        elif st == "likely":
            if prev and prev != names[0]:
                key, ok = "likely→clarify(연속성 충돌) emit", g in (prev, names[0])
            else:
                key, ok = "likely emit", names[0] == g
        elif st == "clarify":
            key, ok = "clarify emit: 정답이 후보에 있음", g in names
            if prev and prev in names:
                buckets["clarify 추천(연속성) 적중"][0] += prev == g
                buckets["clarify 추천(연속성) 적중"][1] += 1
        else:
            a = knn_scores(S, i, labels)
            tot = sum(a.values()) or 1
            top = max(a, key=a.get) if a else None
            n = sum(1 for j in np.argsort(-S[i])[:K + 1]
                    if j != i and labels[j] == top and S[i, j] >= MIN_SIM)
            strong = bool(top and a[top] / tot >= 0.6 and n >= 2)
            tgt = prev or top
            if not tgt:
                key, ok = "none(추론 불가)", False
            elif (prev and prev == top) or (not prev and strong):
                key, ok = "inferred emit", tgt == g
            else:
                key, ok = "inferred 침묵(기록만)", tgt == g
        buckets[key][0] += ok
        buckets[key][1] += 1
    print("\n[넛지 게이트 재현] (keyword-map 은 같은 데이터로 학습 — 약간 낙관적)")
    emitted = sum(v[1] for k, v in buckets.items() if "emit" in k)
    print(f"  넛지 비율 {emitted}/{len(gold)} = {emitted / len(gold):.0%}")
    for k, (ok, n) in sorted(buckets.items(), key=lambda x: -x[1][1]):
        print(f"  {k:34} {ok / max(n, 1):5.0%}  ({ok}/{n})")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-rerank", action="store_true")
    ap.add_argument("--gate", action="store_true", help="넛지 게이트 재현만")
    args = ap.parse_args()

    rows = load()
    kmap = json.loads(KMAP.read_text(encoding="utf-8")) if KMAP.exists() else {}
    labels = [r["target"] for r in rows]
    gold = [i for i, r in enumerate(rows) if r["target_via"] in ("work", "utterance+work")]
    X = similar.embed([r["text"] for r in rows], timeout=300)
    S = X @ X.T

    subsets = {
        "전체": gold,
        "모호키워드": [i for i in gold if any(kmap.get(k, {}).get("status") == "ambiguous"
                                          for k in rows[i].get("keywords") or [])],
        "짧은발화<20": [i for i in gold if len(rows[i]["text"]) < 20],
    }
    cand_sets = {}
    for i in subsets["모호키워드"]:
        cs = set()
        for k in rows[i]["keywords"]:
            if kmap.get(k, {}).get("status") == "ambiguous":
                cs |= {c["project"] for c in kmap[k]["candidates"]} | {kmap[k].get("registered")}
        cand_sets[i] = {c for c in cs if c}

    if args.gate:
        gate_report(rows, S, labels, gold)
        return 0

    preds = defaultdict(dict)
    for i in gold:
        allowed = cand_sets.get(i)
        a = knn_scores(S, i, labels, allowed)
        preds["knn"][i] = pick(a)
        preds["prev"][i] = rows[i]["prev"] if (not allowed or rows[i]["prev"] in allowed) else None
        preds["prev→knn 폴백"][i] = preds["prev"][i] or preds["knn"][i]
        for lam in (0.3, 0.6, 1.0):
            preds[f"knn+prev λ={lam}"][i] = pick(a, rows[i]["prev"], lam, allowed)

    if not args.no_rerank:
        from sentence_transformers import CrossEncoder
        ce = CrossEncoder(RERANKER, max_length=512)
        for i in gold:
            allowed = cand_sets.get(i)
            nb = [j for j in np.argsort(-S[i])[:N_RERANK + 1]
                  if j != i and labels[j] and (not allowed or labels[j] in allowed)]
            if not nb:
                preds["rerank"][i] = None
                continue
            sc = ce.predict([(rows[i]["text"], rows[j]["text"]) for j in nb], show_progress_bar=False)
            agg = defaultdict(float)
            for j, s in sorted(zip(nb, sc), key=lambda x: -x[1])[:K]:
                agg[labels[j]] += float(1 / (1 + np.exp(-s)))   # logit → 0~1
            preds["rerank"][i] = pick(agg)
            preds["rerank+prev λ=0.6"][i] = pick(agg, rows[i]["prev"], 0.6, allowed)
            preds["prev→rerank 폴백"][i] = preds["prev"][i] or preds["rerank"][i]

    base = Counter(labels[i] for i in gold).most_common(1)[0]
    print(f"정답 발화 {len(gold)}건 · 최빈값 기준선 {base[1] / len(gold):.0%} ({base[0]})")
    print(f"{'방식':22}" + "".join(f"{k:>22}" for k in subsets))
    for name, p in preds.items():
        cells = []
        for idx in subsets.values():
            cov = [i for i in idx if p.get(i)]
            acc = sum(p[i] == labels[i] for i in cov) / max(len(cov), 1)
            cells.append(f"{acc:5.0%} (커버 {len(cov)}/{len(idx)})")
        print(f"{name:22}" + "".join(f"{c:>22}" for c in cells))
    return 0


if __name__ == "__main__":
    sys.exit(main())

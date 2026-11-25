#!/usr/bin/env python3
"""vocab_map.py — 작업어휘(SKOS, UD-0004)별 '어느 레포에서 얼마나 쓰였나' 분포를 학습한다.

입력: workspace/utterance-targets.jsonl (tag_targets.py 산출, target_via 에 work 가 있는 발화만)
      + 원장이 가리키는 transcript (원장엔 원문이 없으므로 ref 로 다시 읽는다)
출력: workspace/vocab-term-map.json — uug-grounding `ug.py infer` 의 C3 가 읽는다.
      원문은 저장하지 않는다 (개념·프로젝트·건수만).

C3 (ug.py): 발화의 작업어휘가 직전 작업 레포에서 쓰인 비율(share)이 낮고 다른 레포가 그
어휘를 주로 쓰면, 연속성을 그대로 따르지 않고 그 레포를 추천 후보로 올려 되묻는다.

사용:
  python3 vocab_map.py            # 생성 + 요약
  python3 vocab_map.py --show     # 기존 맵 요약만
"""
import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parents[1]
TAGS = SKILL_DIR / "workspace" / "utterance-targets.jsonl"
OUT = SKILL_DIR / "workspace" / "vocab-term-map.json"
UG_SRC = SKILL_DIR.parent / "uug-grounding" / "src"


def _tag_targets():
    import importlib.util
    p = Path(__file__).resolve().parent / "tag_targets.py"
    spec = importlib.util.spec_from_file_location("tag_targets", p)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def build(tags=TAGS):
    sys.path.insert(0, str(UG_SRC))
    import vocab
    tt = _tag_targets()
    rows = [json.loads(l) for l in open(tags, encoding="utf-8") if l.strip()]
    by_file = defaultdict(dict)   # file → {ref id: target}
    for r in rows:
        # 작업 신호(도구가 건드린 경로)로 정해진 타깃만 쓴다. 발화 키워드로만 정해진 타깃은
        # projects.yaml 키워드('리서치' 등)를 다시 세는 순환이 되므로 제외한다.
        if r.get("target") and "work" in (r.get("target_via") or ""):
            by_file[r["ref"]["file"]][r["ref"]["id"]] = r["target"]

    counts = defaultdict(Counter)    # concept → Counter(project)
    project_n = Counter()            # 프로젝트별 타깃 발화 수 (적용 빈도의 분모)
    seen = missing = 0
    for f, refs in by_file.items():
        if not Path(f).exists():
            missing += len(refs)
            continue
        for turn in tt.transcript_turns(f):
            target = refs.get(turn["ref"])
            if not target:
                continue
            seen += 1
            project_n[target] += 1
            for t in vocab.match_terms(turn["text"]):
                counts[t["concept"]][target] += 1

    out = {"_meta": {"utterances": seen, "missing_refs": missing,
                     "project_n": dict(project_n)}}
    for concept, c in counts.items():
        n = sum(c.values())
        out[concept] = {
            "n": n,
            # share   = 이 어휘가 쓰인 발화 중 그 레포 비율 (어휘 → 레포)
            # rate    = 그 레포 발화 중 이 어휘가 쓰인 비율 (레포에서의 적용 빈도)
            "candidates": [{"project": p, "count": v, "share": round(v / n, 2),
                            "rate": round(v / project_n[p], 3)}
                           for p, v in c.most_common()],
        }
    return out


def show(m):
    meta = m.get("_meta", {})
    print(f"[vocab-map] 발화 {meta.get('utterances')}건 (원문 못 찾은 ref {meta.get('missing_refs')}건)")
    for k, v in sorted(((k, v) for k, v in m.items() if k != "_meta"), key=lambda x: -x[1]["n"]):
        cs = " | ".join(f"{c['project']} {c['share']:.0%}" for c in v["candidates"][:4])
        print(f"  {k:<14} n={v['n']:<4} {cs}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--show", action="store_true")
    args = ap.parse_args()
    if args.show:
        show(json.loads(OUT.read_text(encoding="utf-8")))
        return 0
    if not TAGS.exists():
        print("[vocab-map] 태깅 결과 없음 — tag_targets.py 먼저", file=sys.stderr)
        return 1
    m = build()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(m, ensure_ascii=False, indent=1), encoding="utf-8")
    show(m)
    return 0


if __name__ == "__main__":
    sys.exit(main())

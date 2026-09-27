#!/usr/bin/env python3
"""keyword_map.py — 태깅 결과로 '키워드 → 실제 작업 프로젝트' 분포를 학습한다.

입력: workspace/utterance-targets.jsonl (tag_targets.py 산출, work_target 이 있는 발화만 사용)
출력: workspace/keyword-map.json — uug-grounding `ug.py locate` 가 읽는다.

키워드별 판정:
  exclusive  : top 프로젝트 비율 ≥ EXCLUSIVE_SHARE → 그 프로젝트로 확정해도 안전
  ambiguous  : 2개 이상 프로젝트로 갈라짐 → 추측하지 말고 clarify 질문
  explicit   : 프로젝트 id·aliases(projects.yaml) — 작업 위치와 무관하게 그 프로젝트를 지칭
  (이하 tacit = keywords 에만 적용)
  sparse     : 관측 < MIN_OBS → 판단 보류 (projects.yaml 키워드 그대로 사용)
drift      : projects.yaml 이 가리키는 프로젝트와 실제 top 프로젝트가 다름 (키워드 재배치 후보)

사용:
  python3 keyword_map.py            # 생성 + 요약
  python3 keyword_map.py --show     # 기존 맵 요약만
"""
import argparse
import json
import os
import sys
from collections import Counter, defaultdict
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parents[1]
TAGS = SKILL_DIR / "workspace" / "utterance-targets.jsonl"
OUT = SKILL_DIR / "workspace" / "keyword-map.json"
PROJECTS = SKILL_DIR.parent / "uug-grounding" / "projects.yaml"

MIN_OBS = 3
EXCLUSIVE_SHARE = 0.75
CANDIDATE_SHARE = 0.15   # ambiguous 후보로 노출할 최소 비율


def registered_owner():
    import yaml
    projects = yaml.safe_load(open(PROJECTS, encoding="utf-8")) or {}
    owner, explicit = {}, set()
    for name, p in projects.items():
        for kw in [name] + list(p.get("aliases", [])):
            owner.setdefault(str(kw), name)
            explicit.add(str(kw))
        for kw in p.get("keywords", []):
            owner.setdefault(str(kw), name)
    return owner, explicit


def build():
    rows = [json.loads(l) for l in TAGS.open(encoding="utf-8")]
    dist = defaultdict(Counter)
    for r in rows:
        if r.get("work_target"):
            for kw in r.get("keywords") or []:
                dist[kw][r["work_target"]] += 1
    owner, names = registered_owner()
    out = {}
    for kw, c in dist.items():
        if kw not in owner and not any(kw == n.split(":")[-1] for n in c):
            continue   # tags 등 레지스트리 키워드가 아닌 부분일치 잡음
        sub = next((n for n in c if n.split(":")[-1] == kw), None)
        if kw in names or sub:
            proj = owner.get(kw) or sub
            out[kw] = {"status": "explicit", "n": sum(c.values()),
                       "candidates": [{"project": proj, "share": 1.0}],
                       "registered": owner.get(kw), "drift": False}
            continue
        n = sum(c.values())
        top, tc = c.most_common(1)[0]
        cands = [{"project": p, "share": round(v / n, 2)} for p, v in c.most_common()
                 if v / n >= CANDIDATE_SHARE]
        if n < MIN_OBS:
            status = "sparse"
        elif tc / n >= EXCLUSIVE_SHARE:
            status = "exclusive"
        else:
            status = "ambiguous"
        out[kw] = {"status": status, "n": n, "candidates": cands,
                   "registered": owner.get(kw),
                   "drift": status != "sparse" and owner.get(kw) not in (None, top)}
    return out


def show(m):
    by = defaultdict(list)
    for kw, v in sorted(m.items(), key=lambda x: -x[1]["n"]):
        by[v["status"]].append((kw, v))
    for st in ("ambiguous", "exclusive", "explicit", "sparse"):
        print(f"[{st}] {len(by[st])}개")
        if st in ("sparse", "explicit"):
            continue
        for kw, v in by[st]:
            cs = " | ".join(f"{c['project']} {c['share']:.0%}" for c in v["candidates"])
            flag = f"  ⚠ drift (등록={v['registered']})" if v["drift"] else ""
            print(f"  {kw!r:18} n={v['n']:<3} {cs}{flag}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--show", action="store_true")
    args = ap.parse_args()
    if args.show:
        show(json.loads(OUT.read_text(encoding="utf-8")))
        return 0
    if not TAGS.exists():
        print("[keyword-map] 태깅 결과 없음 — tag_targets.py 먼저", file=sys.stderr)
        return 1
    m = build()
    OUT.write_text(json.dumps(m, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"[keyword-map] {len(m)}개 키워드 → {OUT}")
    show(m)
    return 0


if __name__ == "__main__":
    sys.exit(main())

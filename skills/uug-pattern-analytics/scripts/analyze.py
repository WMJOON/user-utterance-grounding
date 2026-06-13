#!/usr/bin/env python3
"""analyze.py — 발화 패턴 분석 MVP. 발화 모음 → intent 빈도·반복 탐지 → user-pattern(UP) 후보.

uug-grounding 의 lookup(match_intent)을 재사용해 각 발화의 intent 를 분류하고,
빈도·반복(같은 intent 반복 = 워크플로우 패턴/마찰 후보)을 집계한다.
산출 = UP 후보(요약). 실제 기록은 uug-user-memory(wm_node new user-pattern).

사용:
  python3 analyze.py <utterances.jsonl>     # 각 줄: {"utterance": "..."} 또는 평문 1줄
  python3 analyze.py -                       # stdin
MVP 범위: intent 빈도 + 반복. (mso-conversation-analytics 의 DuckDB 전환행렬·
funnel·tier-escalation, 14 의 컨텍스트 최적화 브리핑은 후속 흡수.)
"""
import json
import sys
from collections import Counter
from pathlib import Path

# 팩 내 sibling 스킬 uug-grounding 의 lookup 재사용
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "uug-grounding" / "src"))


def _read(src):
    raw = sys.stdin.read() if src == "-" else Path(src).read_text(encoding="utf-8")
    out = []
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
            out.append(obj.get("utterance", "") if isinstance(obj, dict) else str(obj))
        except ValueError:
            out.append(line)
    return [u for u in out if u]


def main():
    if len(sys.argv) != 2:
        print(__doc__)
        return 1
    try:
        import lookup
    except ImportError:
        print("[ERROR] uug-grounding/src/lookup.py(rdflib) 필요 — 팩 내 sibling 스킬", file=sys.stderr)
        return 1

    utterances = _read(sys.argv[1])
    if not utterances:
        print("[analyze] 발화 없음")
        return 0

    intents = Counter()
    unmatched = 0
    by_intent = {}
    for u in utterances:
        r = lookup.match_intent(u)
        if r["intent"] and not r["ambiguous"]:
            iid = r["intent"]["intent_id"]
            intents[iid] += 1
            by_intent.setdefault(iid, []).append(u)
        else:
            unmatched += 1

    total = len(utterances)
    print(f"[analyze] 발화 {total}개 · 매칭 {total - unmatched} · 미매칭/모호 {unmatched}")
    print("\n=== intent 빈도 ===")
    for iid, c in intents.most_common():
        print(f"  {iid}: {c} ({100*c//total}%)")

    print("\n=== user-pattern(UP) 후보 ===")
    found = False
    for iid, c in intents.most_common():
        if c >= 3:   # 반복 임계 — 워크플로우 패턴/마찰 후보
            found = True
            print(f"  • '{iid}' {c}회 반복 → UP 후보: \"{iid} 워크플로우가 반복됨\"")
            print(f"      예시: {by_intent[iid][:2]}")
    if not found:
        print("  (반복 임계(≥3) 도달 패턴 없음)")
    print("\n→ 기록: uug-user-memory 의 wm_node new user-pattern --title \"...\" 로.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

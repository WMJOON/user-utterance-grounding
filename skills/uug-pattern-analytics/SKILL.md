---
name: uug-pattern-analytics
description: >
  사용자 발화/turns 패턴 탐지·분석. 발화를 uug-grounding 으로 분류해 intent 빈도·
  반복(워크플로우 패턴/마찰)을 측정하고 user-pattern(UP) 후보를 낸다. UP 는
  uug-user-memory 로 기록, grounding 최적화(trigger 정련) 신호로도 쓰인다.
  크로스-프로젝트 user 스코프. mso-conversation-analytics(turn 분석)·
  14_user-pattern-optimizer(발화 마이닝) 흡수 대상.
  다음 상황에서 사용한다: (1) 발화 모음에서 반복 워크플로우·마찰 탐지,
  (2) intent 사용 빈도 측정, (3) UP 후보 추출 → uug-user-memory 기록.
---

# uug-pattern-analytics

발화/turns → 패턴. 크로스-프로젝트 **user 스코프** (MSO intent-레벨 측정·최적화는 `mso-intent-analytics` 별도 — 스코프 다름).

## CLI: `scripts/analyze.py` (MVP)

```bash
python3 scripts/analyze.py <utterances.jsonl>   # 각 줄 {"utterance":"..."} 또는 평문
python3 scripts/analyze.py -                     # stdin
```
- uug-grounding 의 `match_intent`(TTL lookup)로 각 발화 intent 분류 (팩 내 sibling 재사용).
- 산출: intent 빈도 + 반복(≥3) UP 후보. 기록은 uug-user-memory `wm_node new user-pattern`.

## 흡수 로드맵

- **MVP (현재)**: intent 빈도 + 반복 탐지 → UP 후보.
- **후속**: `mso-conversation-analytics` 흡수 — DuckDB turns 전환행렬·funnel·reprompt율. ⚠ MSO tier-escalation 폐루프 신호는 MSO 로 emit 하거나 MSO 잔류분과 협의.
- **후속**: `14_user-pattern-optimizer` 흡수 — Claude Code 트랜스크립트 직접 마이닝·미사용 스킬 탐지·컨텍스트 최적화 브리핑(PreCompact/Stop 훅).

## 스코프 경계

UP(크로스-프로젝트 user-레벨 행동) ↔ work-memory PT(프로젝트-레벨 패턴). 프로젝트 PT 가 ≥2 프로젝트에서 반복되면 uug-user-memory 로 `derived-from` 승격(planning §2).

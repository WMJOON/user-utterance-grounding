---
name: uug-pattern-analytics
description: >
  [⏳ PLANNED — 미구현 stub] 사용자 발화/turns 패턴 탐지·분석. 반복 워크플로우·마찰
  지점·intent 사용 패턴을 측정해 user-pattern(UP) 엔트리로 피드하고, uug-grounding
  의 trigger/매칭 최적화 신호를 낸다. mso-conversation-analytics(turn 분석)와
  14_user-pattern-optimizer(발화 마이닝)를 흡수. 크로스-프로젝트 user 스코프.
---

# uug-pattern-analytics  ⏳ PLANNED

> 미구현 stub. 설계 정본: [planning/user-memory-architecture.md](../../../planning/user-memory-architecture.md) (§11).

## 역할 (예정)

- 발화/turns 패턴 측정: 반복 워크플로우, 수정 요청, 마찰 지점, intent 사용 빈도·전환.
- 산출: **user-pattern(UP)** 엔트리(uug-user-memory 로) + grounding 최적화 신호(trigger_keywords 정련).
- 스코프: **크로스-프로젝트 user-레벨**. (MSO intent-레벨 측정·최적화는 MSO `mso-intent-analytics` 가 별도 담당 — 스코프 다름.)

## 흡수 대상

- `mso-conversation-analytics` (turns.jsonl 분석·전환행렬·reprompt율). ⚠ MSO tier-escalation 폐루프 신호는 MSO 로 emit 하거나 MSO 잔류분과 협의.
- `14_user-pattern-optimizer` (트랜스크립트 발화 패턴·미사용 스킬 탐지·컨텍스트 최적화 브리핑).

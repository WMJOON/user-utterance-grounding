---
name: uug-user-memory
description: >
  [⏳ PLANNED — 미구현 stub] 사용자 스코프 영속 메모리(UC/UP/UF). MSO work-memory
  의 user 스코프 쌍둥이 — schema-driven wm 엔진(vendored)을 재사용한다. 발화·작업에서
  user-context/user-preference 를 기록하고 zvec 시맨틱 검색·graph traversal 을 제공.
  uug-pattern-analytics 가 user-pattern(UP)을 피드한다. 설계: planning §3·§4·§8-3b.
---

# uug-user-memory  ⏳ PLANNED (§8-3b)

> 미구현 stub. 빌드는 user-memory 코어 단계(§8-3b)에서. 설계 정본: [planning/user-memory-architecture.md](../../../planning/user-memory-architecture.md).

## 역할 (예정)

- **티어**: `user-context`(UC) · `user-pattern`(UP) · `user-preference`(UF). reference 는 제외(world → `_reference/`).
- **엔진**: MSO `mso-work-memory` 의 schema-driven `wm_node.py`(타입 schema.yaml 로딩, MSO v0.3.4) 를 vendoring 재사용. jsonl + zvec + graph.
- **데이터 레이어**: vault 루트 별도 계층(§9 위치 미정). 스킬=엔진/툴링, 데이터=별도(MSM 패턴).
- **always-on 티어**: 정체성+활성 선호+승격 원칙을 SessionStart 로 주입(작게·캡). 나머지 pull.

## 흡수 대상 (§8-4/§8-5)

- agent personal-memory (markdown → UC/UF 번역; `reference` 타입은 `_reference/` 로 split)
- `03_personal-memory`(personal-memory-wrapper 툴링)

## 미해결 (planning §9)

데이터레이어 위치/이름, always-on 캡, 승격 임계값(≥2 프로젝트 vs 프로젝트 내 반복).

---
name: uug-orchestration
description: >
  user-utterance-grounding(UUG) 스킬팩의 라우터/진입점. 사용자 발화를 받아
  적절한 UUG 스킬로 라우팅한다. MSO mso-orchestration · MSM msm-orchestration 과
  동일한 orchestration 패턴. 다음 상황에서 사용한다:
  (1) 사용자 발화의 타깃 프로젝트·intent가 불분명할 때 grounding 으로 먼저 정렬,
  (2) grounded intent 에 따라 기록(user-memory)·패턴분석·프로젝트 액션으로 분기,
  (3) UUG 팩 전반의 정책(scope 규율·HITL·PII 가드) 강제.
---

# uug-orchestration

UUG 스킬팩의 **정책·라우팅 레이어**. 발화를 grounding 한 뒤 결과 intent를 팩 내 적절한 스킬로 보낸다.

## 스킬팩 구성 (members)

| 스킬 | 역할 | 상태 |
|---|---|---|
| **uug-orchestration** | 라우터/진입점 + 정책 (이 스킬) | ✅ |
| **uug-grounding** | 발화 → {target_project, intent, slots} 정렬 + intent TTL/lookup + 위치 index + UserPromptSubmit 값전달 | ✅ |
| **uug-user-memory** | UC/UP/UF 영속(vendored schema-driven wm 엔진 + bootstrap) | ✅ |
| **uug-pattern-analytics** | 발화→intent 빈도·반복 탐지 → user-pattern 후보 (MVP; DuckDB·14 흡수는 후속) | ✅ MVP |

## 라우팅 (utterance → action)

```
발화 → uug-grounding (utterance→intent 정렬)
     ├─ intent=record-memory  → uug-user-memory (scope=user/project 라우팅)
     ├─ 도메인 intent(프로젝트) → ug dispatch: 그 프로젝트의 뒷단 CLI 에 subprocess 위임
     │                          (예: MSO dispatch_ticket → mso-intent-analytics/src/pipeline.py)
     ├─ 패턴 회고/최적화        → uug-pattern-analytics
     └─ 모호/신호0             → HITL (프로젝트·intent 명시 요청)
```

**배선 (§11 UUG→프로젝트 단방향 의존)**: 도메인 intent 는 `projects.yaml` 의 `dispatch`
선언(kind=cli, entry)에 따라 `ug dispatch "<발화>"` 가 그 프로젝트 CLI 를 subprocess 호출한다.
UUG 가 앞단(utterance→intent), 프로젝트가 뒷단(intent→action). **피호출 프로젝트는 UUG 를
import 하지 않는다** — 프로세스 경계로 독립 테스트성 보존. dispatch 미선언 프로젝트/user intent
는 UUG 자체 grounding 결과로 폴백.

## 정책 (always-on)

- **scope 규율**: world(`_reference/`) / project(work-memory) / user(user-memory) 혼동 금지. UUG는 user·크로스-프로젝트 스코프.
- **utterance→intent = UUG / intent→workflow-action = 해당 프로젝트(MSO 등)**. 경계 침범 금지 (planning §11).
- **PII 가드**: 공개 단위 push 전 `uug-grounding/check-private.sh` 통과 필수.
- **HITL**: grounding 모호·필수 슬롯 미충족 시 사용자 확인.

## 관련

- 설계 정본: `01_user-utterance-grounding/planning/user-memory-architecture.md`
- 선례: MSO `mso-orchestration`, MSM `msm-orchestration`.

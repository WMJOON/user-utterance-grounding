---
name: uug-orchestration
version: "0.0.5"
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
- **user-memory ≠ project worklog**: UUG 기본 영속 타입은 UC/UP/UF다. workflow node 실행 기록은 각 프로젝트 work-memory가 소유한다.
- **preference proposal ≠ slot spec mutation**: MSO workflow 상의 task rail/slot 명세는 MSO가 소유한다. UUG는 반복 이벤트와 user preference entity를 기억해 adjusted entity-filling 또는 proposal을 제공할 수 있지만, workflow slot spec을 직접 수정하지 않는다.
- **MSO/MSM 편의 레이어**: MSO는 workflow/work-memory를, MSM(가칭)은 ontology KB와 AI 추론 경로 제약을 소유한다. UUG는 둘을 사용할 때 target/intent/entity-filling 편의를 제공한다.
- **hook side effect 금지**: UserPromptSubmit hook은 grounding context 주입만 수행하고 기록·dispatch·worklog 생성을 하지 않는다.
- **MSO v0.6.3 throttle 경계**: Stop reminder throttle은 project provider hook의 사용자 출력 억제 정책이다. UUG 기본 hook은 UserPromptSubmit 값전달이므로 Stop throttle을 등록하지 않는다.
- **PII 가드**: 공개 단위 push 전 `uug-grounding/check-private.sh` 통과 필수.
- **HITL**: grounding 모호·필수 슬롯 미충족 시 사용자 확인.

## 관련

- 설계 정본: `01_user-utterance-grounding/planning/user-memory-architecture.md`
- 선례: MSO `mso-orchestration`, MSM `msm-orchestration`.

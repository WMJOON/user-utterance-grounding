---
name: uug-user-memory
version: "0.0.5"
description: >
  사용자 스코프 영속 메모리(UC/UP/UF) — MSO work-memory 의 user 스코프 쌍둥이.
  schema-driven wm 엔진(vendored)을 재사용해 user-context/user-pattern/
  user-preference 를 jsonl + zvec + graph 로 자산화한다. 스킬=엔진, 데이터=별도
  레이어(MSM 패턴, bootstrap.py 로 init). uug-pattern-analytics 가 UP 를 피드한다.
  다음 상황에서 사용한다: (1) 사용자/환경 사실·선호 기록, (2) "전에 이거 어떻게
  하기로 했지?" 시맨틱 검색, (3) graph traversal, (4) 프로젝트 work-memory 의
  원칙이 ≥2 프로젝트에서 반복되면 derived-from 으로 승격.
---

# uug-user-memory

user 스코프 메모리. work-memory(프로젝트)와 **엔진 공유, 타입만 다름**.
MSO v0.6.3 기준에 따라 project worklog는 이 스코프의 기본 타입이 아니다.

## 티어 (schema.yaml = SSOT)

| prefix | 타입 | 담는 것 |
|---|---|---|
| **UC** | user-context | 사용자·환경·프로젝트 사실 |
| **UP** | user-pattern | 관측된 행동 규칙 (uug-pattern-analytics 피드) |
| **UF** | user-preference | 선호·작업 방식 |

reference 는 제외(world scope → `_reference/`). intent 정렬은 `uug-grounding`.
`worklog`/`auditlog`는 project workflow 실행·감사 레이어의 타입이며, UUG user-memory는 UC/UP/UF만 쓴다.

## 구성 (스킬=엔진 / 데이터=별도 레이어)

| 파일 | 역할 |
|---|---|
| `scripts/wm_node.py` | **vendored** (MSO mso-work-memory, schema-driven v0.3.4). new/validate/search/graph/stats. provenance 헤더 — 상류 drift 시 재동기화 |
| `scripts/simple_kb.py` | **vendored** zvec 검색 백엔드 (wm_node 가 자기 옆에서 1순위 탐색) |
| `schema.yaml` | UC/UP/UF 타입 + relation 어휘. 데이터레이어로 복제됨 |
| `scripts/bootstrap.py` | `<target-dir>` 에 인스턴스 init (티어 디렉토리 + schema 복사) |
| `scripts/task_rail_projection.py` | turns.jsonl + UC/UP/UF metadata 에서 선호 task rail JSONL projection 생성/query/drift 탐지. MSO workflow slot spec은 수정하지 않고 entity-filling proposal만 만든다 |
| `references/json-schema/task-rail-preferences.schema.json` | task rail preference JSONL record schema |
| `references/jsonl-queries/task-rail.jq` | task rail 선호/표류/slot adjustment 조회용 jq 예시 |

## 사용

```bash
pip install pyyaml zvec
python3 scripts/bootstrap.py <data-layer-dir>      # 인스턴스 생성 (위치는 사용자 선택)
WORKMEM_DIR=<data-layer-dir> python3 scripts/wm_node.py new user-context --title "..." --tags a,b
WORKMEM_DIR=<data-layer-dir> python3 scripts/wm_node.py search "전에 어떻게 하기로 했지"
python3 scripts/task_rail_projection.py build --user-memory <data-layer-dir> --projects <projects.yaml> --turns workspace/.mso-context/conversation/turns.jsonl
python3 scripts/task_rail_projection.py query --user-memory <data-layer-dir> --intent <intent_id>
python3 scripts/task_rail_projection.py drift --user-memory <data-layer-dir> --projects <projects.yaml>
```

- **데이터레이어 위치**: 사용자 선택(예: vault 루트 별도 계층). 절대경로 하드코딩 없음. (planning §9 위치/이름 미확정.)
- **always-on 티어**: 정체성+활성 선호+승격 원칙을 SessionStart 로 주입(작게·캡) — 후속.
- `new`/`validate`/`graph` 는 zvec 없이도 동작. `search`/`reindex` 만 zvec 필요.
- UserPromptSubmit hook이나 cloud runtime side effect를 user-memory hand-off 보장으로 보지 않는다. 영속해야 하는 내용은 UC/UP/UF entry 또는 tracked file에 명시적으로 남긴다. MSO v0.6.3의 Stop reminder throttle은 project Stop reminder에만 적용되며, UUG user-memory 타입/hand-off 계약은 바꾸지 않는다.
- **task rail preference projection**: `graph/task-rail-preferences.jsonl`은 사용자 발화·UC/UP/UF에서 파생된 읽기 전용 추천 record다. MSO workflow의 task rail/slot 명세는 그대로 두고, 반복 이벤트·패턴에서 `observed_entity_filling`과 `adjusted_entity_filling`을 만들어 entity-filling proposal로 제공한다. `decision_drift_status`와 `bias_correction_status`는 사용자 결정 drift와 편향 보정 검토 상태를 분리해 담는다. `graph/task-rail-drift.jsonl`은 프로젝트 workflow/node 참조가 사라졌는지 감지하지만, project workflow TTL을 수정하지 않는다.
- **repository context projection**: `repository -> task_rail_preference -> slot_adjustments[]`가 1차 spine이다. `context/repositories/`는 mso-enabled repository 종류와 위치·상태를 수동/자동 curated entry로 담는 컨벤션이고, projection은 `projects.yaml` 및 turns/UC/UP/UF metadata에서 repository object를 만든다.
- **고도화 대상**: `pattern/episodic/`과 `user_pattern`/`episodic_memory` record는 다음 단계에서 반복 이벤트, episode, drift/bias 보정 이력을 더 엄밀히 모델링하기 위한 확장점이다.

## 흡수 (planning §8-4/§8-5)

agent personal-memory(markdown → UC/UF; `reference` 는 `_reference/` 로 split), `03_personal-memory`(personal-memory-wrapper 툴링). **라이브 이주는 사용자 확인 후.**

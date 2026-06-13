---
name: uug-user-memory
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

## 티어 (schema.yaml = SSOT)

| prefix | 타입 | 담는 것 |
|---|---|---|
| **UC** | user-context | 사용자·환경·프로젝트 사실 |
| **UP** | user-pattern | 관측된 행동 규칙 (uug-pattern-analytics 피드) |
| **UF** | user-preference | 선호·작업 방식 |

reference 는 제외(world scope → `_reference/`). intent 정렬은 `uug-grounding`.

## 구성 (스킬=엔진 / 데이터=별도 레이어)

| 파일 | 역할 |
|---|---|
| `scripts/wm_node.py` | **vendored** (MSO mso-work-memory, schema-driven v0.3.4). new/validate/search/graph/stats. provenance 헤더 — 상류 drift 시 재동기화 |
| `scripts/simple_kb.py` | **vendored** zvec 검색 백엔드 (wm_node 가 자기 옆에서 1순위 탐색) |
| `schema.yaml` | UC/UP/UF 타입 + relation 어휘. 데이터레이어로 복제됨 |
| `scripts/bootstrap.py` | `<target-dir>` 에 인스턴스 init (티어 디렉토리 + schema 복사) |

## 사용

```bash
pip install pyyaml zvec
python3 scripts/bootstrap.py <data-layer-dir>      # 인스턴스 생성 (위치는 사용자 선택)
WORKMEM_DIR=<data-layer-dir> python3 scripts/wm_node.py new user-context --title "..." --tags a,b
WORKMEM_DIR=<data-layer-dir> python3 scripts/wm_node.py search "전에 어떻게 하기로 했지"
```

- **데이터레이어 위치**: 사용자 선택(예: vault 루트 별도 계층). 절대경로 하드코딩 없음. (planning §9 위치/이름 미확정.)
- **always-on 티어**: 정체성+활성 선호+승격 원칙을 SessionStart 로 주입(작게·캡) — 후속.
- `new`/`validate`/`graph` 는 zvec 없이도 동작. `search`/`reindex` 만 zvec 필요.

## 흡수 (planning §8-4/§8-5)

agent personal-memory(markdown → UC/UF; `reference` 는 `_reference/` 로 split), `03_personal-memory`(personal-memory-wrapper 툴링). **라이브 이주는 사용자 확인 후.**

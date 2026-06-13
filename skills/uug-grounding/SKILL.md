---
name: uug-grounding
description: >
  사용자가 특정 {project-name} 을 명시하지 않은 발화에서, intent 유형으로 타깃
  프로젝트를 추론(grounding)한다. 또 프로젝트 위치를 머신-이식 가능한 레지스트리
  (projects.yaml + machine.yaml 앵커)로 관리·해석한다. MSO mso-utterance-grounding
  의 유저/크로스-프로젝트 평행. 다음 상황에서 사용한다:
  (1) "이거 정리하자"·"착수해줘" 처럼 프로젝트 미명시 요청의 타깃 추론,
  (2) 프로젝트 식별자 → 현재 머신의 절대경로 해석(resolve),
  (3) 멀티머신 경로 drift 점검(doctor),
  (4) (이후) user-memory(UC/UP/UF) 영속·검색.
  status: MVP (grounding + 인덱스/리졸버). 메모리 레이어는 후속.
---

# uug-grounding

발화를 **타깃 프로젝트로 grounding** 하고, 프로젝트 위치를 **머신 무관**으로 해석하는 스킬셋. 설계 정본: [planning/user-memory-architecture.md](../../../planning/user-memory-architecture.md) (§1.5 핵심 기능).

## CLI: `scripts/ug.py` (pyyaml 필요)

```bash
python3 scripts/ug.py ground "<발화>"   # 발화 → 타깃 프로젝트 추론 (Lv10 keyword)
python3 scripts/ug.py resolve <project> # project → 이 머신 절대경로
python3 scripts/ug.py doctor            # 레지스트리 경로 존재 확인 (✓/✗/⚠)
python3 scripts/ug.py list              # 등록 프로젝트
```

## 구성

**두 레이어** — 의미(intent/slot, TTL) vs 위치(project 경로, yaml):

| 파일 | 싱크 | 역할 |
|---|---|---|
| `instances/user_intents.ttl` | 싱크됨 | **★ intent SoT (엄밀 TTL)** — intent + slot_specs + trigger_keywords |
| `references/schemas/nlu_intent.yaml` | 싱크됨 | LinkML schema (OWL/SHACL/JSON-schema 생성용) |
| `taxonomy/*.ttl` | 싱크됨 | SKOS verb/target 위계 |
| `src/lookup.py` | 싱크됨 | RDFLib 소비 API (`list_intents`/`lookup_intent`/`match_intent`) |
| `tools/build.sh` | 싱크됨 | LinkML → OWL/SHACL/JSON-schema (dev 전용, linkml 필요) |
| `projects.yaml` | 싱크됨 | 프로젝트 위치 레지스트리 — `{project: {anchor, rel, keywords, tags}}` (절대경로 없음). `target_project` 슬롯 해석 소스 |
| `machine.yaml` | **gitignore** | 이 머신의 `anchors: {name: 절대경로}` |
| `machine.example.yaml` | 싱크됨 | 새 머신용 템플릿 |

> **MSM 패턴**: intent 는 축약 yaml 이 아니라 엄밀 TTL 로 정의(SoT)하고, RDFLib(lookup.py)로 컨버팅해 런타임 소비. mso-intent-registry 구조를 복사·adapt(직접 의존 X).

- **머신 이식**: 경로를 `{anchor, rel}` 로 저장(싱크), 머신마다 다른 절대경로는 machine.yaml(로컬). `$CLAUDE_PROJECT_DIR` 이식 원칙과 동일.
- **0-config 부트스트랩**: machine.yaml 없으면 `.obsidian` 마커를 위로 탐지해 `vault` 앵커 자동 생성. vault 밖 레포만 앵커 수동 추가.
- **grounding (slot 기반, Lv10)**: 발화 → `match_intent`(TTL trigger_keywords) 로 intent 분류 → slot fill(`ask`=발화추출 / `session_context`=추론 / `default`) → 필수 슬롯 미충족 시 reprompt(HITL). `target_project` 슬롯의 `session_context` 가 "project-name 미명시 → 추론"의 핵심(MVP: projects.yaml 키워드 매칭; `last_project` 세션추적은 후속). Lv30 LLM fallback 후속.

## 상태

MVP — grounding + 인덱스/리졸버/doctor 동작. user-memory(UC/UP/UF) 영속 레이어와 user-pattern 자동 피더는 planning §8-3b 이후.

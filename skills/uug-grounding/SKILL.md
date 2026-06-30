---
name: uug-grounding
version: "0.0.5"
description: >
  사용자가 특정 {project-name} 을 명시하지 않은 발화에서, intent 유형으로 타깃
  프로젝트를 추론(grounding)한다. 또 프로젝트 위치를 머신-이식 가능한 레지스트리
  (projects.yaml + machine.yaml 앵커)로 관리·해석한다. MSO v0.6.3 기준
  utterance→intent 앞단을 맡고, intent→action 뒷단은 각 프로젝트(MSO는
  mso-intent-analytics)에 위임한다. 다음 상황에서 사용한다:
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
| `projects.yaml` | 싱크됨 | 프로젝트 위치 레지스트리 — `{project: {anchor, rel, keywords, tags, intent_registry?}}` (절대경로 없음). `target_project` 슬롯 해석 소스 + (선택) 도메인 레지스트리 경로 |
| `machine.yaml` | **gitignore** | 이 머신의 `anchors: {name: 절대경로}` |
| `machine.example.yaml` | 싱크됨 | 새 머신용 템플릿 |

> **MSM 패턴**: intent 는 축약 yaml 이 아니라 엄밀 TTL 로 정의(SoT)하고, RDFLib(lookup.py)로 컨버팅해 런타임 소비. mso-intent-registry 구조를 복사·adapt(직접 의존 X).

> **멀티-레지스트리 브리지 (§11 전제 #1)**: `lookup.py` 는 **namespace-agnostic** — intent/술어를 로컬명 기준으로 읽어 `uug:`·`mso:` 및 임의 프로젝트 레지스트리를 합쳐 ground 한다. `projects.yaml` 의 `intent_registry`(프로젝트 루트 상대 TTL 경로) 선언 시 그 도메인 intent 가 grounding 에 포함되고, 매칭되면 `source_project` 로 target_project 가 함의된다. MSO 운영 intent(`dispatch_ticket`·`query_audit_log` 등)를 UUG 가 ground → orchestration 이 `intent_id` 를 MSO `mso-intent-analytics` 뒷단에 전달.

- **머신 이식**: 경로를 `{anchor, rel}` 로 저장(싱크), 머신마다 다른 절대경로는 machine.yaml(로컬). `$CLAUDE_PROJECT_DIR` 이식 원칙과 동일.
- **0-config 부트스트랩**: machine.yaml 없으면 `.obsidian` 마커를 위로 탐지해 `vault` 앵커 자동 생성. vault 밖 레포만 앵커 수동 추가.
- **grounding (slot 기반, Lv10)**: 발화 → `match_intent`(TTL trigger_keywords) 로 intent 분류 → slot fill(`ask`=발화추출 / `session_context`=추론 / `default`) → 필수 슬롯 미충족 시 reprompt(HITL). `target_project` 슬롯의 `session_context` 가 "project-name 미명시 → 추론"의 핵심(MVP: projects.yaml 키워드 매칭; `last_project` 세션추적은 후속). Lv30 LLM fallback 후속.

## 상태

MVP — grounding + 인덱스/리졸버/doctor 동작. user-memory(UC/UP/UF) 영속 레이어와 user-pattern 자동 피더는 planning §8-3b 이후.

## Hook 경계 (MSO v0.6.3 정렬)

`UserPromptSubmit` hook은 grounding context를 stdout으로 주입하는 값전달 레이어다. 기록, dispatch,
worklog 생성 side effect를 수행하지 않으며 항상 prompt를 막지 않는다. cloud/ephemeral runtime에서는
hook side effect를 다음 에이전트 기억 보장으로 보지 않는다.

다른 repository 테스트나 provider runtime에서 UUG 개입을 끄고 싶을 때는 환경변수를 사용한다.

| 변수 | 효과 |
|---|---|
| `UUG_HOOKS_DISABLED=1` | UserPromptSubmit hook만 조용히 비활성화한다. CLI는 계속 사용 가능하다. |
| `UUG_DISABLED=1` | hook과 `ug ground`/`ug dispatch`를 no-op으로 비활성화한다. |
| `UUG_ENABLED=0` | `UUG_DISABLED=1`과 같은 전역 비활성화 alias. |

Codex 등록은 `.codex/config.toml`을 canonical hook 표면으로 쓴다. v0.0.3의 `.codex/hooks.json`
UUG 등록은 중복 실행 방지를 위해 installer가 제거한다. `hooks.json`은 다른 provider/legacy 설정을
임의로 비우지 않고, UUG가 만든 `UserPromptSubmit` command만 정리한다.

MSO v0.6.3의 `stop-check.sh` throttle은 Stop reminder 출력에 대한 정책이다. UUG의 기본 hook은
`UserPromptSubmit` 값전달 hook이므로 Stop reminder throttle을 등록하지 않는다.

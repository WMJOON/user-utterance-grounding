---
name: uug-grounding
version: "0.4.0"
description: >
  사용자가 특정 {project-name} 을 명시하지 않은 발화에서, intent 유형으로 타깃
  프로젝트를 추론(grounding)한다. 또 프로젝트 위치를 머신-이식 가능한 레지스트리
  (projects.yaml + machine.yaml 앵커)로 관리·해석한다. MSO mso-utterance-grounding
  의 유저/크로스-프로젝트 평행. 다음 상황에서 사용한다:
  (1) "이거 정리하자"·"착수해줘" 처럼 프로젝트 미명시 요청의 타깃 추론,
  (2) 프로젝트 식별자 → 현재 머신의 절대경로 해석(resolve),
  (3) 멀티머신 경로 drift 점검(doctor),
  (4) 발화가 지칭하는 프로젝트 디렉토리 추론(ug locate / ug infer): explicit(id·aliases)
      확정, tacit(keywords)은 학습 분포로 추정·clarify, 키워드 없으면 직전 턴 작업 경로(연속성)
      → 유사 발화 폴백. 매 프롬프트 UserPromptSubmit 훅(ug-locate-hook, Claude Code·Codex; Antigravity는 PreInvocation).
  user-memory(UC/UP/UF)는 uug-user-memory 가 담당.
---

# uug-grounding

발화를 **타깃 프로젝트로 grounding** 하고, 프로젝트 위치를 **머신 무관**으로 해석하는 스킬셋. 설계 정본: [planning/user-memory-architecture.md](../../../planning/user-memory-architecture.md) (§1.5 핵심 기능).

## CLI: `scripts/ug.py` (pyyaml 필요)

```bash
python3 scripts/ug.py ground "<발화>"   # 발화 → 타깃 프로젝트 추론 (Lv10 keyword)
python3 scripts/ug.py resolve <project> # project → 이 머신 절대경로
python3 scripts/ug.py doctor            # 레지스트리 경로 존재 확인 (✓/✗/−/⚠) + rdflib 점검
python3 scripts/ug.py locate "<발화>"   # 지칭 프로젝트 디렉토리 (keyword-map 상 모호하면 clarify)
python3 scripts/ug.py infer "<발화>" --transcript <jsonl> [--log]   # 키워드+연속성+유사발화 → emit 판정 JSON
python3 scripts/ug.py list              # 등록 프로젝트
```

## locate 훅 (Claude Code + Codex + Antigravity)

Claude·Codex는 `hooks/ug-locate-hook.py`, Antigravity는 `hooks/ug-antigravity-hook.py`를 등록한다(`install.sh` 기본값, v0.3.1~. legacy `ug-prompt-hook` 은 `--prompt-hook`). 매 발화에 `ug.py infer` 를 돌려(~0.2s)
explicit(프로젝트 id·`aliases`) 은 대상 디렉토리 안내, tacit(`keywords`) 은 추정(likely) 또는 모호 시 clarify,
키워드가 없으면 연속성(payload `transcript_path` 의 직전 턴 작업 경로) → 유사 발화 폴백으로 추론한다.

| 클라이언트 | 등록 위치 | 출력 |
|---|---|---|
| Claude Code | `~/.claude/settings.json` → `hooks.UserPromptSubmit` | plain stdout |
| Codex | `~/.codex/config.toml` → `[features] hooks = true` + `[[hooks.UserPromptSubmit]]` (`--codex`) | `hookSpecificOutput.additionalContext` JSON |
| Antigravity app/CLI/IDE | `~/.gemini/config/hooks.json` → `uug-grounding.PreInvocation` (`--antigravity`) | `injectSteps[].ephemeralMessage` JSON |

- 넛지는 `emit=true` 일 때만 (키워드 없음이면 직전 작업과 유사 발화가 일치하거나, 직전 없이 유사 발화가 강할 때).
  같은 디렉토리도 대상 저장소의 작업 시작 계약을 전달한다. 모든 판정은 `~/.local/share/uug/locate-log.jsonl` 에 원문 없이 기록.
- Codex 는 새 훅을 **신뢰(trust) 승인 전까지 조용히 건너뛴다.** 등록 후 대화형 `codex` 에서 `/hooks` 로 한 번 승인한다.
- 같은 로직을 프로젝트별 사본으로도 등록하면 넛지가 중복되므로 한 곳(전역)에만 등록한다.
- 실측(`uug-pattern-analytics/scripts/eval_targets.py --gate`, 345건): inferred 넛지 87%·clarify 후보 포함 94%·연속성 추천 94% 적중.

## 구성

**두 레이어** — 의미(intent/slot, TTL) vs 위치(project 경로, yaml):

| 파일 | 싱크 | 역할 |
|---|---|---|
| `instances/user_intents.ttl` | 싱크됨 | **★ intent SoT (엄밀 TTL)** — intent + slot_specs + trigger_keywords + `scope`(후보 공간 위계: meta/repository/workflow/workflow.executionRail, UD-0001. 현재는 lookup 노출만 — 후보 바인딩 정책은 후속) |
| `references/schemas/nlu_intent.yaml` | 싱크됨 | LinkML schema (OWL/SHACL/JSON-schema 생성용) |
| `taxonomy/*.ttl` | 싱크됨 | SKOS verb/target 위계 |
| `src/lookup.py` | 싱크됨 | RDFLib 소비 API (`list_intents`/`lookup_intent`/`match_intent`) |
| `tools/build.sh` | 싱크됨 | LinkML → OWL/SHACL/JSON-schema (dev 전용, linkml 필요) |
| `projects.yaml` | 싱크됨 | 프로젝트 위치 레지스트리 — `{project: {anchor, rel, keywords, tags, intent_registry?}}` (절대경로 없음). `target_project` 슬롯 해석 소스 + (선택) 도메인 레지스트리 경로 |
| `machine.yaml` | **gitignore** | 이 머신의 `anchors: {name: 절대경로}` |
| `machine.example.yaml` | 싱크됨 | 새 머신용 템플릿 |

> **MSM 패턴**: intent 는 축약 yaml 이 아니라 엄밀 TTL 로 정의(SoT)하고, RDFLib(lookup.py)로 컨버팅해 런타임 소비. mso-intent-analytics 구조를 복사·adapt(직접 의존 X).

> **멀티-레지스트리 브리지 (§11 전제 #1)**: `lookup.py` 는 **namespace-agnostic** — intent/술어를 로컬명 기준으로 읽어 `uug:`·`mso:` 및 임의 프로젝트 레지스트리를 합쳐 ground 한다. `projects.yaml` 의 `intent_registry`(프로젝트 루트 상대 TTL 경로) 선언 시 그 도메인 intent 가 grounding 에 포함되고, 매칭되면 `source_project` 로 target_project 가 함의된다. MSO 운영 intent(`dispatch_ticket`·`query_audit_log` 등)를 UUG 가 ground → orchestration 이 `intent_id` 를 mso-utterance-grounding 뒷단에 전달.

- **머신 이식**: 경로를 `{anchor, rel}` 로 저장(싱크), 머신마다 다른 절대경로는 machine.yaml(로컬). `$CLAUDE_PROJECT_DIR` 이식 원칙과 동일.
- **0-config 부트스트랩**: machine.yaml 없으면 `.obsidian` 마커를 위로 탐지해 `vault` 앵커 자동 생성. vault 밖 레포만 앵커 수동 추가.
- **grounding (slot 기반, Lv10)**: 발화 → `match_intent`(TTL trigger_keywords) 로 intent 분류 → slot fill(`ask`=발화추출 / `session_context`=추론 / `default`) → 필수 슬롯 미충족 시 reprompt(HITL). `target_project` 슬롯의 `session_context` 가 "project-name 미명시 → 추론"의 핵심(MVP: projects.yaml 키워드 매칭; `last_project` 세션추적은 후속). Lv30 LLM fallback 후속.
- **ambiguous fallback (top-2 margin)**: `match_intent` 가 top-1·top-2 점수차(`margin`, 후보 1개면 None)를 산출하고, `margin < 임계` 면 commit 대신 `ambiguous`(HITL, 임계 창 내 후보 나열, rc 2). 임계는 스코프별 env 로 튜닝 — user `UG_AMBIGUOUS_MARGIN_USER`(기본 1: 동점만 HITL), 도메인 `UG_AMBIGUOUS_MARGIN_DOMAIN`(기본 0: 동점도 top-1 commit, §11.1 first-match-wins 비회귀). 동점 commit 은 결과의 `committed_low_margin`(dispatch JSON 은 `uug_margin`/`uug_committed_low_margin`)으로 관측 → uug-pattern-analytics 임계 튜닝 재료. 실측(fixture 50발화)상 오답은 margin 0 에 집중, margin ≥ 1 은 전건 정답이라 기본 임계 상향은 무익 — 키워드 가중 스코어링으로 margin 해상도 확보가 후속.

## 상태

MVP — grounding + 인덱스/리졸버/doctor 동작. user-memory(UC/UP/UF) 영속 레이어와 user-pattern 자동 피더는 planning §8-3b 이후.

## Codex 작업 시작 계약 (2026-10-11)

- Codex 사용자 기록의 `response_item/message(role=user)`와 `item_completed/UserMessage`를 모두 읽고, 같은 입력의 이중 기록은 한 턴으로 합친다. 기존 event ID는 증분 태깅 참조로 보존한다.
- 키워드 없는 명시적 짧은 제어 발화(이어서·계속·그만 등)는 transcript의 직전 타깃에 연결한다. 활성 컨텍스트가 없으면 확정하지 않는다. 이는 대상 안내이며 pause/cancel 실행 승인이 아니다.
- `hooks/context_contract.py`가 대상과 후속 조회 절차를 생성한다. 새 작업·대상 전환이면 AGENTS/CLAUDE 및 대상 work-memory를 읽고 ID·경로·적용 제약 또는 기록 없음/조회 실패를 보고한다. 같은 작업에서 이미 읽은 근거는 재사용한다.
- 같은 디렉토리도 계약을 전달한다. clarify는 대상 확인만 전달하고, likely는 확인 후 진행한다. 훅은 작업 실행이나 기록 쓰기를 하지 않는다.
- 검증: `python3 -m pytest skills/uug-grounding/tests/test_codex_context.py -q` (repository 루트). 이 테스트는 transcript→추론→전달 계약을 검증하며 실제 모델의 행동 준수는 별도 대화 관측이 필요하다.

## Antigravity 연결

`bash install.sh --antigravity`는 UUG 팩의 네 스킬을 전역 discovery에 연결하고 기존 다른 훅을 보존한다.
`--all`은 세 클라이언트를 포함한다. `--prompt-hook`은 Antigravity와 함께 쓰지 않는다.
`transcriptPath`·`workspacePaths`의 camelCase payload와 실제 USER_INPUT/PLANNER_RESPONSE 기록을 소비한다.
사용자 요청만 추출하고 시스템 주입·슬래시 명령 확장 메타데이터를 제외한다. 도구 루프에서는 반복 주입하지 않는다.
별도 세션 상태를 쓰지 않고 현재 transcript로 판단한다. 로그는 기존 원문 없는 infer 판정 로그만 사용한다.
검증: `python3 -m pytest skills/uug-grounding/tests/test_antigravity_context.py -q`.

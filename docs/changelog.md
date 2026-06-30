# 변경 이력

## v0.0.5 (2026-06-30) — MSO v0.6.3 user-scope 정렬

> **MSO v0.6.3의 Stop reminder throttle을 UUG 경계에 맞춰 해석하고, user-memory projection을 JSONL-first로 정리했다.** UUG는 UserPromptSubmit 값전달과 user-scope preference/proposal을 담당하며, MSO workflow/task rail/slot spec은 수정하지 않는다.

### Changed

| 변경 | 내용 |
|------|------|
| Stop reminder 경계 | UUG의 자동 hook은 `UserPromptSubmit` 값전달 레이어이며 Stop reminder가 아니다. 따라서 `stop-check.sh` 같은 Stop throttle은 UUG 기본 설치 대상이 아니다. |
| hook side effect | `UserPromptSubmit` hook은 계속 기록, dispatch, worklog 생성 side effect를 수행하지 않는다. |
| on/off switch | 다른 repository 테스트에서 UUG 개입을 끌 수 있도록 `UUG_HOOKS_DISABLED=1`, `UUG_DISABLED=1`, `UUG_ENABLED=0` 환경변수를 지원한다. |
| Codex hook 표면 | Codex hook 등록 표면은 계속 `.codex/config.toml`을 canonical로 두고, legacy `.codex/hooks.json` UUG 등록만 제거한다. |
| hand-off 기준 | hook side effect는 hand-off 보장이 아니며, 영속 인계는 UC/UP/UF entry 또는 tracked file에 명시적으로 남긴다. |
| task rail preference projection | `task_rail_projection.py`가 발화/UC/UP/UF metadata에서 `graph/task-rail-preferences.jsonl`을 만든다. UUG는 MSO workflow의 task rail/slot 명세를 수정하지 않고, 반복 이벤트·패턴에서 user preference entity를 기억해 adjusted entity-filling proposal을 낸다. |
| drift/bias signal | workflow/node drift와 별도로 user decision drift, bias correction 상태를 추적한다. |
| projection schema | user-memory projection schema는 `repository -> task_rail_preference -> slot_adjustments[]`를 1차 spine으로 둔다. `context/repositories/`에는 mso-enabled repository context를, `pattern/episodic/`에는 향후 반복 이벤트/episode 기반 drift·bias 보정 근거를 쌓는다. |

## v0.0.4 (2026-06-30) — MSO v0.6.2 user-scope 정렬

> **MSO v0.6.2의 work-memory/hook/cloud hand-off 원칙을 UUG의 user-scope에 맞게 번역했다.**

### Changed

| 변경 | 내용 |
|------|------|
| user-memory 타입 | UUG의 기본 영속 기록 단위는 `user-context`(UC), `user-pattern`(UP), `user-preference`(UF)다. project-scope `worklog`는 UUG user-memory의 기본 타입이 아니다. |
| prompt hook 의미 | `UserPromptSubmit` hook은 grounding context를 stdout으로 주입하는 값전달 레이어다. 기록, dispatch, worklog 생성 side effect를 수행하지 않는다. |
| Codex canonical config | Codex hook 등록 표면은 `.codex/config.toml`을 canonical로 둔다. `.codex/hooks.json`의 구 UUG UserPromptSubmit 등록은 중복 실행 방지를 위해 제거한다. |
| cloud hand-off | cloud/ephemeral runtime에서는 hook side effect를 다음 에이전트 기억 보장으로 보지 않는다. 인계가 필요하면 최종 답변, diff, 커밋 가능한 tracked file에 남긴다. |
| project workflow 경계 | project workflow 실행 기록은 각 프로젝트(MSO/MSM 등)의 work-memory가 소유한다. UUG는 utterance→intent 앞단과 user-scope 기억만 담당한다. |

## v0.0.3 (2026-06-30) — Codex UserPromptSubmit 적용

> **Codex 공식 Hooks 문서에서 `UserPromptSubmit` 이벤트와 stdout context 주입 지원을 확인하고, Codex에서도 UUG 자동 grounding 훅을 등록하도록 정정했다.**

### Changed

| 변경 | 내용 |
|------|------|
| Codex install | `bash install.sh --codex`는 `~/.codex/skills/uug-grounding` 링크와 `~/.codex/config.toml`의 `UserPromptSubmit` 훅을 함께 등록한다. |
| matcher | Codex의 `UserPromptSubmit`은 현재 `matcher`를 사용하지 않으므로 matcher 없이 등록한다. |
| provider path | 같은 `hooks/ug-prompt-hook.py`를 사용하되, Claude는 `~/.claude/skills/...`, Codex는 `~/.codex/skills/...` 경로로 호출한다. |
| hook side effect | hook은 context 주입만 수행하며 기록·dispatch·worklog 생성을 하지 않는다. |
| legacy hooks.json | v0.0.3에서 쓰던 `~/.codex/hooks.json` UUG 등록은 installer가 제거한다. Codex가 두 설정 표면을 모두 읽는 런타임에서 같은 prompt hook이 두 번 실행되는 것을 막기 위한 v0.6.2 정렬이다. |

참고:
- [OpenAI Codex Hooks — UserPromptSubmit](https://developers.openai.com/codex/hooks#userpromptsubmit)
- [OpenAI Codex Hooks — Matcher patterns](https://developers.openai.com/codex/hooks#matcher-patterns)

## v0.0.2 (2026-06-30) — Provider-Free 적용

> **Claude Code의 기존 `UserPromptSubmit` 기반 자동 grounding 성능을 유지하면서 Codex에서도 UUG 스킬셋을 사용할 수 있도록 설치/라우팅 경계를 정리했다.**

### Changed

| 변경 | 내용 |
|------|------|
| Claude 기본 설치 | 기본 `install.sh` 동작은 기존과 동일하게 Claude Code 대상이다. `~/.claude/skills/uug-grounding` 링크와 `~/.claude/settings.json`의 `UserPromptSubmit` 훅을 유지한다. |
| Codex 링크 설치 | Codex에서는 `bash install.sh --codex` 또는 글로벌 sync를 통해 `~/.codex/skills/uug-*` 링크를 설치한다. |
| Codex prompt hook | v0.0.2 시점에는 Codex `UserPromptSubmit` 훅을 보수적으로 제외했으나, v0.0.3에서 공식 문서 기준으로 등록 경로를 추가했다. |
| all mode | `--all`은 Claude Code + Codex 링크와 자동 발화 훅을 함께 구성한다. |
| MSO 경계 | MSO와의 경계는 유지한다. UUG는 utterance→intent 앞단을 담당하고, intent→action 뒷단은 MSO 또는 각 프로젝트 dispatch가 담당한다. |

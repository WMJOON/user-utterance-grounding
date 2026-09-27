# 변경 이력

## v0.3.1 (2026-09-27) — `ug-locate-hook` 을 설치 기본값으로, 문서 정합성

> **`install.sh` 가 기본으로 `hooks/ug-locate-hook.py` 를 등록한다.** v0.3.0 에서 새 훅을 추가했지만 설치 스크립트는 여전히 legacy `ug-prompt-hook` 을 등록했고, README 는 locate 훅을 따로 등록하라고 해 두 훅이 함께 돌 수 있었다. patch 로 낸 이유: CLI·스키마 계약 변경 없이 설치 기본값과 문서를 v0.3.0 기능에 맞춘 정정이다. legacy 훅은 `--prompt-hook` 으로 그대로 쓸 수 있다.

### Changed

| 변경 | 내용 |
|------|------|
| `install.sh` 기본 훅 | `ug-prompt-hook.py` → `ug-locate-hook.py` (Codex 는 `--codex` 인자 포함). `--prompt-hook` 으로 legacy 선택. |
| 기존 등록 교체 | 재실행 시 이전에 등록된 UUG 훅(두 종류 모두)을 지우고 하나만 남긴다. 다른 훅은 보존. 멱등. |
| Codex 안내 | 설치 후 대화형 `codex` 의 `/hooks` 에서 신뢰 승인이 필요하다고 출력. |
| hook side effect 원칙 | "기록 금지" → "user-memory·dispatch·worklog 금지, `ug infer --log` 판정 로그(원문 없음)만 예외"로 명시 (README·uug-orchestration). |

### Docs

| 변경 | 내용 |
|------|------|
| README 빠른 시작 | 두 훅의 차이 표, `ug` 가 `python3 skills/uug-grounding/scripts/ug.py` 의 줄임이라는 안내, `ug list` 추가, 수동 등록 예시는 install.sh 대안으로 정리. |
| README 다이어그램 | 기본 locate/infer 경로(clear·likely·clarify·inferred·침묵)와 학습 산출물 흐름 추가. |
| 의존성 | 핵심은 Python 3.9+, 유사 발화(zvec)만 3.10+ 로 정정. |
| SKILL 설명문 | uug-grounding·uug-pattern-analytics·uug-orchestration(0.0.6) 설명과 라우팅에 locate/infer·태깅 반영. |

## v0.3.0 (2026-09-27) — 발화별 타깃 태깅 + `locate`/`infer` (explicit·tacit, 연속성, 유사 발화)

> **발화마다 "어느 프로젝트를 지칭했는가"를 태깅하고, 그 이력으로 매 프롬프트 지칭 대상을 추론하는 경로를 추가했다.** minor bump 사유: 새 CLI 계약 표면(`locate`, `infer`), 레지스트리 새 필드(`aliases`), 새 훅, pattern-analytics 신규 스크립트 4종. 기존 `ground`/`dispatch`/`resolve` 동작은 그대로다(하위호환).

### Added

| 변경 | 내용 |
|------|------|
| `aliases` (explicit) / `keywords` (tacit) | `projects.yaml` 키워드를 두 종류로 구분. explicit(프로젝트 id·별칭)은 항상 확정, tacit(주제 암시)은 학습 분포로 판정. |
| `ug locate "<발화>"` | 지칭 프로젝트 디렉토리 추론. `clear`(explicit) / `likely`(tacit 단일) / `clarify`(tacit 모호·충돌) / `none`. `--similar` 로 clarify 후보에 유사 발화 기준 추천. |
| `ug infer "<발화>" --transcript <jsonl>` | 키워드 + **연속성**(transcript 직전 턴에서 도구가 건드린 경로) + **유사 발화** 폴백 → `emit` 판정 JSON. `--log` 로 판정을 원문 없이 `~/.local/share/uug/locate-log.jsonl` 에 기록. |
| `hooks/ug-locate-hook.py` | `infer` 를 매 프롬프트 호출(~0.2s)해 신뢰도가 높을 때만 1줄 주입. Claude Code(plain stdout) / Codex(`--codex`, `additionalContext` JSON) 공용. 현재 세션 디렉토리와 같은 대상이면 침묵. |
| `machine.yaml hosts.<hostname>.anchors` | 머신별 앵커 오버레이. 동기화되는 `machine.yaml` 에 여러 머신 경로가 섞여도 hostname 섹션이 공통 `anchors` 위에 덮어쓴다. `null` = 이 머신에 없는 루트(doctor `−`). |
| `ug doctor` | 실행 python 경로와 `rdflib` 설치 여부를 점검. |
| pattern-analytics `tag_targets.py` | Claude Code·Codex 트랜스크립트의 발화마다 `utterance_target`(발화 키워드) / `work_target`(그 턴의 도구 경로 역해석) / `disagree` 를 태깅. **원문은 저장하지 않고** ref(file+id)만. 엄브렐러의 미등록 서브모듈은 `<umbrella>:<sub>` 로 분리. |
| pattern-analytics `keyword_map.py` | 키워드 → 실제 작업 프로젝트 분포 학습(`explicit`/`exclusive`/`ambiguous`/`sparse` + `drift`). `locate` 가 소비. |
| pattern-analytics `similar.py` | 타깃 확정 발화를 zvec 에 색인(벡터 + target/ref, 원문 없음). 임베딩 `BAAI/bge-m3` — OpenAI 호환 로컬 임베딩 서버(`UUG_EMBED_URL`) 우선, 실패 시 sentence-transformers 로컬 로드. |
| pattern-analytics `eval_targets.py` | 추론 방식 leave-one-out 비교 + `--gate` 로 `infer` 넛지 규칙 재현. |

### Fixed

| 변경 | 내용 |
|------|------|
| 영문 키워드 경계 | 영숫자 키워드는 더 긴 토큰의 일부면 불일치(`UUG` ⊄ `uug-locate`). 뒤에 한글 조사가 붙는 경우는 일치. |
| 중첩 서브모듈 귀속 | 등록 프로젝트 안쪽의 서브모듈을 별도 프로젝트로 떼어내지 않는다. |

### 실측 (작성자 환경, 작업 경로로 정답이 확인된 발화 345건, leave-one-out)

| 방식 | 정확도 |
|------|--------|
| 최빈값 기준선 | 32% |
| 유사 발화 kNN (bge-m3) | 49% |
| cross-encoder 리랭커 (bge-reranker-v2-m3) | 50% — 이득 없음, 채택 안 함 |
| 연속성 (직전 턴 타깃) | 78% (커버 90%) |
| 연속성 → kNN 폴백 | 77% (커버 ~100%) |

`infer` 넛지 규칙 재현: 키워드 없이 추론해 넛지한 경우 87%, clarify 후보에 정답 포함 94%, 연속성 추천 94% 적중. 짧은 한국어 요청문("~해줘")끼리 내용과 무관하게 0.98 로 뭉치는 `paraphrase-multilingual-MiniLM` 대신 `bge-m3` 를 쓴다.

### Known issues

- `tests/test_bridge.py` 2건 실패(29 통과) — 이번 변경과 무관. 도메인 레지스트리(MSO `intents.ttl`) 트리거가 좁아져 브리지 fixture(예: "wf-abc 중단해")가 미매칭된다. 트리거와 fixture 중 어느 쪽을 맞출지는 도메인 레지스트리 쪽 결정이 필요하다.

## v0.2.0 (2026-07-22) — `ground --json` 추가 (dispatch 미경유 값전달)

> **`ug.py ground`에 `--json` 출력 모드를 추가했다.** minor bump 사유: 새 CLI 계약 표면(플래그) 추가(하위호환, 비파괴) — 기존 `ground`/`--for-hook` 동작은 그대로다. `intent_id`/`target_project`/`target_path`만 필요한 소비자(예: 프로젝트별 uug-context-hook)가 `dispatch`(도메인 프로젝트 뒷단 위임, nested subprocess)를 거치지 않고 `_do_ground()` 결과를 그대로 받을 수 있다.

### Added

| 변경 | 내용 |
|------|------|
| `ground --json` | `_do_ground()` 결과 dict를 한 줄 JSON으로 출력. `dispatch_to_project()`를 전혀 거치지 않는다(그건 `dispatch` 전용 경로). status가 `no-intent`/`ambiguous`면 rc=2, 그 외 rc=0 — `dispatch --json`과 동일한 관례. |

### 배경

프로젝트별 `uug-context-hook.py`(work-on-project 넛지)는 지금까지 `dispatch --json` + `resolve` 두 단계를 썼다. 이 훅이 필터링하는 intent(기본 `work-on-project`)는 항상 user-scope(도메인 아님)라 `dispatch_to_project()`의 도메인 위임 결과는 매번 버려지는데도, 엉뚱한 도메인 intent가 매칭될 때마다 nested subprocess(v0.1.1로 8s 상한)를 대가로 치렀다. `ground --json` 한 번으로 필요한 값을 모두 얻어 이 비용을 없앤다.

## v0.1.1 (2026-07-22) — dispatch 내부 subprocess 타임아웃 정합성 수정

> **`ug dispatch`가 도메인 프로젝트 뒷단(예: MSO pipeline.py)에 위임할 때 쓰던 inner subprocess timeout을 30s → 8s로 낮췄다.** patch bump 사유: 계약·스키마 변경 없는 안정성 수정. 호출측(uug-context-hook.py 등 UserPromptSubmit 훅)이 `ug.py dispatch`를 outer timeout=10s로 감싸는 것을 전제로 하는데, inner가 30s였던 탓에 도메인 dispatch가 오래 걸리는 발화에서 훅이 outer가 강제 종료할 때까지 불필요하게 붙잡혀 매 프롬프트 지연(최대 관측치 30s)을 유발했다.

### Fixed

| 변경 | 내용 |
|------|------|
| dispatch inner timeout | `ug.py`의 `dispatch_to_project()` subprocess timeout을 `30 → 8`로 조정 — outer 훅 예산(10s) 안에서 항상 자체적으로 종료되도록 정렬. |

## v0.1.0 (2026-07-04) — candidate-bound grounding 1단계 (margin fallback + intent scope)

> **grounding 판정에 top-2 margin 기반 ambiguous fallback 을 배선하고, intent taxonomy 에 후보 공간 위계(scope) 축을 도입했다.** minor bump 사유: grounding 결과 계약에 새 status(`ambiguous`)와 관측 필드가 추가되고, intent SoT 에 새 축(`uug:scope`)이 생겼다. 기본값은 전부 비회귀(기존 동작 동일) — 이번 릴리스는 측정·노출 레이어이며 후보 바인딩 정책은 2단계.

### Added

| 변경 | 내용 |
|------|------|
| top-2 margin 산출 | `lookup.match_intent` 가 `top2_score`/`margin`(top-1 − top-2, 후보 1개면 None)을 반환. `ambiguous` 는 `margin == 0` 의 파생값(하위호환). |
| ambiguous fallback | `margin < 임계` 면 commit 대신 `status=ambiguous`(HITL, rc 2, 임계 창 내 후보 나열). 임계는 스코프별 env — `UG_AMBIGUOUS_MARGIN_USER`(기본 1: 동점만 HITL, 구 ambiguous 동일) / `UG_AMBIGUOUS_MARGIN_DOMAIN`(기본 0: 동점도 top-1 commit, MSO first-match-wins 비회귀, fixture 84% ≥ 80% 유지). |
| margin 관측 | 동점 commit 은 `committed_low_margin`(구 `committed_ambiguous` 대체), `ug dispatch --json` 에 `uug_margin`/`uug_committed_low_margin` — uug-pattern-analytics 임계 튜닝 재료. |
| intent scope 축 | `user_intents.ttl` 전 intent 에 `uug:scope` 선언(meta / repository / workflow / workflow.executionRail). `nlu_intent.yaml` 에 `ScopeEnum`. lookup 은 scope 노출만 — scope 미선언 레지스트리(도메인 등)는 `None`(비파괴). |

### Design decisions (모노레포 working-memory/user-decision)

| 결정 | 내용 |
|------|------|
| topicChange = scope 전이 | 별도 감지기가 아니라 rail 활성 중 발화가 repository/workflow scope 로 ground 되는 것 자체가 신호. repository/workflow intent 는 rail 활성 중에도 후보 공간에서 제거하지 않는다(escape 경로). (UD-0001) |
| meta.dialog_feedback | "중단해"·"네" 류 짧은 제어 발화는 meta scope 이며 rail 이탈이 아니다 — referent 는 활성 컨텍스트가 해소. (UD-0002) |
| excursion | rail 진행 중 read-only 조회는 taxonomy 이동 없이 전이 정책 `f(scope, verb_class, rail 활성)` 로 처리 — QueryVerb=excursion(복귀), 변경 verb=topic change(HITL). (UD-0002) |

### 실측 근거

fixture 50발화: 오답은 margin 0(동점)에 집중(4/12), margin ≥ 1 은 전건 정답(2/2) → 기본 임계 상향은 무익. margin 해상도 확보(키워드 가중/edge count)가 2단계 선행 과제.

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

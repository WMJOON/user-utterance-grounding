# user-utterance-grounding

발화의 intent로 **타깃 프로젝트를 추론(grounding)**하는 스킬셋 — 사용자가 `{project-name}`을 명시하지 않아도 어느 프로젝트에 대한 요청인지 해석한다. 프로젝트 위치는 머신-무관 레지스트리(`projects.yaml` 앵커 + `machine.yaml`)로 관리.

> **§11 NLU 경계**: UUG = **utterance→intent**(앞단, 크로스-프로젝트). intent→action(뒷단)은 각 프로젝트가 소유. 도메인 intent 는 `ug dispatch` 가 `projects.yaml` 의 `dispatch`(kind=cli, entry) 선언에 따라 그 프로젝트의 CLI 를 **subprocess 위임**한다 — 피호출 프로젝트는 UUG 를 import 하지 않는다(단방향 의존, 프로세스 경계). 예: MSO `dispatch_ticket` → `mso-intent-analytics/src/pipeline.py`.

> **현재 비공개(private). 추후 공개 예정.** 코드에 개인정보·절대경로 하드코딩 없음(전부 `__file__`/`.obsidian` 자동탐지/env/anchor). 사용자 데이터(`projects.yaml`·`machine.yaml`·`.session.json`)는 gitignore, 배포는 `*.example.yaml`만. push 전 `check-private.sh` PII 체크 필수.

## 스킬팩 구성 (orchestration 패턴 — MSO/MSM 류)

| 스킬 | 역할 | 상태 |
|---|---|---|
| `uug-orchestration` | 라우터/진입점 + 정책 | ✅ |
| `uug-grounding` | 발화 → {target_project, intent, slots} + intent TTL/lookup + 위치 index + UserPromptSubmit 값전달 + `ug dispatch`(도메인 intent → 프로젝트 CLI 위임) | ✅ |
| `uug-user-memory` | UC/UP/UF 영속(vendored schema-driven wm 엔진 + bootstrap) | ✅ |
| `uug-pattern-analytics` | 발화→intent 빈도·반복 탐지 → user-pattern 후보 | ✅ MVP |

## 설치

```bash
cd skills/uug-grounding
pip install rdflib pyyaml
cp projects.example.yaml projects.yaml   # 본인 프로젝트 등록
bash install.sh                          # ~/.claude/skills 심링크 + UserPromptSubmit 훅 등록
ug use <project>                         # 현재 작업 프로젝트 고정(선택)
```

> **멀티-머신**: `vault` 앵커는 `machine.yaml` 에 절대경로를 적지 않아도 된다 — `ug` 가 `.obsidian` 마커를 탐지해 런타임 자가복구한다(iCloud 동기로 `machine.yaml` 이 머신 간 복제돼도 오염 안 됨). vault 밖 레포 앵커(code 등)만 `machine.yaml` 에 추가.

상세: [`skills/uug-grounding/SKILL.md`](skills/uug-grounding/SKILL.md).

# user-utterance-grounding

발화의 intent로 **타깃 프로젝트를 추론(grounding)**하는 스킬셋 — 사용자가 `{project-name}`을 명시하지 않아도 어느 프로젝트에 대한 요청인지 해석한다. 프로젝트 위치는 머신-무관 레지스트리(`projects.yaml` 앵커 + `machine.yaml`)로 관리. MSO `mso-utterance-grounding`의 유저/크로스-프로젝트 평행.

> **현재 비공개(private). 추후 공개 예정.** 코드에 개인정보·절대경로 하드코딩 없음(전부 `__file__`/`.obsidian` 자동탐지/env/anchor). 사용자 데이터(`projects.yaml`·`machine.yaml`·`.session.json`)는 gitignore, 배포는 `*.example.yaml`만. push 전 `check-private.sh` PII 체크 필수.

## 설치

```bash
cd skills/user-utterance-grounding
pip install rdflib pyyaml
cp projects.example.yaml projects.yaml   # 본인 프로젝트 등록
bash install.sh                          # ~/.claude/skills 심링크 + UserPromptSubmit 훅 등록
ug use <project>                         # 현재 작업 프로젝트 고정(선택)
```

상세: [`skills/user-utterance-grounding/SKILL.md`](skills/user-utterance-grounding/SKILL.md).

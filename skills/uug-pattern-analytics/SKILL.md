---
name: uug-pattern-analytics
version: "0.1.0"
description: >
  사용자 발화/turns 패턴 탐지·분석. 발화를 uug-grounding 으로 분류해 intent 빈도·
  반복(워크플로우 패턴/마찰)을 측정하고 user-pattern(UP) 후보를 낸다. UP 는
  uug-user-memory 로 기록, grounding 최적화(trigger 정련) 신호로도 쓰인다.
  크로스-프로젝트 user 스코프. mso-conversation-analytics(turn 분석)·
  14_user-pattern-optimizer(발화 마이닝) 흡수 대상.
  다음 상황에서 사용한다: (1) 발화 모음에서 반복 워크플로우·마찰 탐지,
  (2) intent 사용 빈도 측정, (3) UP 후보 추출 → uug-user-memory 기록.
---

# uug-pattern-analytics

발화/turns → 패턴. 크로스-프로젝트 **user 스코프** (MSO intent-레벨 측정·최적화는 `mso-intent-analytics` 별도 — 스코프 다름).

## CLI: `scripts/analyze.py` (MVP)

```bash
python3 scripts/analyze.py <utterances.jsonl>   # 각 줄 {"utterance":"..."} 또는 평문
python3 scripts/analyze.py -                     # stdin
```
- uug-grounding 의 `match_intent`(TTL lookup)로 각 발화 intent 분류 (팩 내 sibling 재사용).
- 산출: intent 빈도 + 반복(≥3) UP 후보. 기록은 uug-user-memory `wm_node new user-pattern`.

## CLI: `scripts/tag_targets.py` — 발화별 타깃 태깅

```bash
python3 scripts/tag_targets.py            # 증분 (Claude Code + Codex 트랜스크립트)
python3 scripts/tag_targets.py --rebuild  # projects.yaml 변경 후 전체 재태깅
python3 scripts/tag_targets.py --summary  # 집계만
```
- 발화 1건 = 1줄 → `workspace/utterance-targets.jsonl` (gitignore). **원문은 저장하지 않고** `ref`(file+id)만 남긴다.
- 신호 두 가지: `utterance_target`(발화 시점 intent·키워드) / `work_target`(그 턴에서 도구가 건드린 경로 → 레지스트리 루트 역해석). 최종 `target` 은 work 우선.
- `disagree=true` = 두 신호 불일치 → 과하게 넓은 키워드·트리거 정련 재료.
- `.gitmodules` 가 있는 엄브렐러 아래의 미등록 서브모듈은 `<umbrella>:<sub>` 로 분리 태깅 → 레지스트리 등록 후보.

## CLI: `scripts/keyword_map.py` — 키워드 → 실제 작업 프로젝트 분포

```bash
python3 scripts/keyword_map.py   # workspace/keyword-map.json 생성 + 요약 (tag_targets.py 뒤에 실행)
```
- 키워드별 `explicit`(프로젝트 이름) / `exclusive`(한쪽으로 모임) / `ambiguous`(갈라짐) / `sparse`(관측 부족) 판정, `drift`=등록 소유자와 실제 top 불일치.
- 소비자: uug-grounding `ug.py locate` — ambiguous 면 clarify(추측 금지), 확정이면 대상 디렉토리 안내.

## CLI: `scripts/similar.py` — 유사 발화(zvec) 기반 후보 재정렬

```bash
# 1회 셋업 (zvec 은 Python ≥3.10, venv 는 iCloud 밖에)
python3.11 -m venv ~/.local/share/uug/venv
~/.local/share/uug/venv/bin/pip install zvec sentence-transformers pyyaml rdflib
V=~/.local/share/uug/venv/bin/python
$V scripts/similar.py index              # 타깃 확정 발화 색인 (증분, --rebuild)
$V scripts/similar.py query "<발화>" --candidates a,b
```
- 임베딩 `BAAI/bge-m3`(1024d). `paraphrase-multilingual-MiniLM` 은 한국어 요청문끼리 0.98 로 뭉쳐 부적합.
- 색인: `~/.local/share/uug/zvec-utterances` (머신 로컬). 벡터 + target/ref 만, 원문 없음.
- 실측(LOO, 모호 키워드 발화 62건): 후보 내 top1 69% (무작위 39%), 비중 ≥0.6·이웃 ≥2 이면 80%.
  → **자동 확정에 쓰지 않는다.** `ug.py locate --similar` 가 clarify 후보에 `★추천` 을 붙이는 용도.

## CLI: `scripts/eval_targets.py` — 추론 방식 비교 (LOO)

```bash
$V scripts/eval_targets.py --no-rerank   # knn / 연속성(prev) / 결합 비교
$V scripts/eval_targets.py               # + cross-encoder 리랭커 (bge-reranker-v2-m3, ~5분)
$V scripts/eval_targets.py --gate        # ug.py infer 넛지 규칙 재현 → 상태별 적중·넛지 비율
```
2026-09-27 결과(345건): 최빈값 32%, knn 49%, 리랭커 50%(이득 없음), 연속성 78%, 연속성→knn 폴백 77%(커버 ~100%).
→ 연속성이 주 신호, 유사 발화는 폴백·보강. 리랭커·ColBERT 는 보류.
- 임베딩은 omlx 상주 `BAAI/bge-m3`(`~/.omlx/model_settings.json` pinned, ~20ms)를 쓰고 실패 시 로컬 로드로 폴백.

## 갱신 순서
`tag_targets.py` → `keyword_map.py` → `similar.py index`

## 흡수 로드맵

- **MVP (현재)**: intent 빈도 + 반복 탐지 → UP 후보.
- **후속**: `mso-conversation-analytics` 흡수 — DuckDB turns 전환행렬·funnel·reprompt율. ⚠ MSO tier-escalation 폐루프 신호는 MSO 로 emit 하거나 MSO 잔류분과 협의.
- **후속**: `14_user-pattern-optimizer` 흡수 — Claude Code 트랜스크립트 직접 마이닝·미사용 스킬 탐지·컨텍스트 최적화 브리핑(PreCompact/Stop 훅).

## 스코프 경계

UP(크로스-프로젝트 user-레벨 행동) ↔ work-memory PT(프로젝트-레벨 패턴). 프로젝트 PT 가 ≥2 프로젝트에서 반복되면 uug-user-memory 로 `derived-from` 승격(planning §2).

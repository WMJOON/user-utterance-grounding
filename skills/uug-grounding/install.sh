#!/usr/bin/env bash
# install.sh — uug-grounding 글로벌 설치 (사용자가 직접 실행).
#   1) 스킬을 ~/.claude/skills/ 에 심링크 (경로 머신-무관: ~ 로 해석)
#   2) UserPromptSubmit 훅을 ~/.claude/settings.json 에 등록 (merge, 멱등)
# 에이전트는 이 스크립트를 *실행하지 않는다* — 설정 자기수정 가드 때문. 사용자가 실행.
# 끄기: ~/.claude/settings.json 의 해당 UserPromptSubmit 블록 삭제 + 심링크 제거.
set -euo pipefail

SKILL_SRC="$(cd "$(dirname "$0")" && pwd)"
SKILL_NAME="uug-grounding"
GLOBAL_SKILL="$HOME/.claude/skills/$SKILL_NAME"
SETTINGS="$HOME/.claude/settings.json"
# 머신-무관 경로: 런타임에 $HOME 로 해석되도록 리터럴 보존
HOOK_CMD='python3 "$HOME/.claude/skills/uug-grounding/hooks/ug-prompt-hook.py"'

echo "uug-grounding 설치"
echo "  소스: $SKILL_SRC"

# 1) 심링크
mkdir -p "$HOME/.claude/skills"
ln -sfn "$SKILL_SRC" "$GLOBAL_SKILL"
echo "[1] 심링크: ~/.claude/skills/$SKILL_NAME → 소스"

# 2) 훅 등록 (merge, 멱등) — python3 로 JSON 안전 병합
python3 - "$SETTINGS" "$HOOK_CMD" <<'PY'
import json, os, sys
settings_path, cmd = sys.argv[1], sys.argv[2]
os.makedirs(os.path.dirname(settings_path), exist_ok=True)
try:
    s = json.load(open(settings_path, encoding="utf-8"))
except (FileNotFoundError, ValueError):
    s = {}
ups = s.setdefault("hooks", {}).setdefault("UserPromptSubmit", [])
if any(h.get("command") == cmd for g in ups for h in g.get("hooks", [])):
    print("[2] UserPromptSubmit 훅 이미 등록됨 — skip")
else:
    ups.append({"hooks": [{"type": "command", "command": cmd}]})
    json.dump(s, open(settings_path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"[2] UserPromptSubmit 훅 등록 → {settings_path}")
PY

echo "[3] 의존성:  pip install rdflib pyyaml"
echo "[4] 설정:"
echo "      - projects.yaml 에 본인 프로젝트 등록 (projects.example.yaml 복사)"
echo "      - machine.yaml 은 첫 실행 시 .obsidian 자동탐지로 부트스트랩 (또는 machine.example.yaml 복사)"
echo "      - ug use <project> 로 현재 작업 프로젝트 고정 → 신호0 발화도 추론"
echo "완료. 다음 세션부터 매 발화 자동 grounding."

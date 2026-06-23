#!/usr/bin/env bash
# install.sh — uug-grounding 글로벌 설치 (사용자가 직접 실행).
#   기본값: Claude Code 설치
#   --codex: Codex skill 링크 + UserPromptSubmit 훅 등록
#   --all: Claude Code + Codex
#   1) 스킬을 ~/.{claude,codex}/skills/ 에 심링크 (경로 머신-무관: ~ 로 해석)
#   2) UserPromptSubmit 훅을 provider 설정 파일에 등록 (merge, 멱등)
# 에이전트는 이 스크립트를 *실행하지 않는다* — 설정 자기수정 가드 때문. 사용자가 실행.
# 끄기: ~/.claude/settings.json 또는 ~/.codex/hooks.json 의 해당 UserPromptSubmit 블록 삭제 + 심링크 제거.
set -euo pipefail

SKILL_SRC="$(cd "$(dirname "$0")" && pwd)"
SKILL_NAME="uug-grounding"
# 머신-무관 경로: 런타임에 $HOME 로 해석되도록 리터럴 보존
CLAUDE_HOOK_CMD='python3 "$HOME/.claude/skills/uug-grounding/hooks/ug-prompt-hook.py"'
CODEX_HOOK_CMD='python3 "$HOME/.codex/skills/uug-grounding/hooks/ug-prompt-hook.py"'

TARGETS=()
for arg in "$@"; do
  case "$arg" in
    --codex) TARGETS+=(codex) ;;
    --all) TARGETS+=(claude codex) ;;
    --claude) TARGETS+=(claude) ;;
    -h|--help)
      sed -n '1,12p' "$0"
      exit 0
      ;;
    *) ;;
  esac
done
[ ${#TARGETS[@]} -eq 0 ] && TARGETS=(claude)

echo "uug-grounding 설치"
echo "  소스: $SKILL_SRC"
echo "  대상: ${TARGETS[*]}"

install_link() {
  local target="$1"
  local global_skill="$HOME/.$target/skills/$SKILL_NAME"
  mkdir -p "$HOME/.$target/skills"
  ln -sfn "$SKILL_SRC" "$global_skill"
  echo "[1] 심링크: ~/.$target/skills/$SKILL_NAME → 소스"
}

install_claude_hook() {
  local settings="$HOME/.claude/settings.json"
  python3 - "$settings" "$CLAUDE_HOOK_CMD" <<'PY'
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
}

install_codex_hook() {
  local hooks_json="$HOME/.codex/hooks.json"
  python3 - "$hooks_json" "$CODEX_HOOK_CMD" <<'PY'
import json, os, sys
hooks_path, cmd = sys.argv[1], sys.argv[2]
os.makedirs(os.path.dirname(hooks_path), exist_ok=True)
try:
    s = json.load(open(hooks_path, encoding="utf-8"))
except (FileNotFoundError, ValueError):
    s = {}
ups = s.setdefault("hooks", {}).setdefault("UserPromptSubmit", [])
if any(h.get("command") == cmd for g in ups for h in g.get("hooks", [])):
    print("[2] Codex UserPromptSubmit 훅 이미 등록됨 — skip")
else:
    ups.append({
        "hooks": [{
            "type": "command",
            "command": cmd,
            "timeout": 15,
            "statusMessage": "Grounding user prompt"
        }]
    })
    json.dump(s, open(hooks_path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"[2] Codex UserPromptSubmit 훅 등록 → {hooks_path}")
PY
}

for target in "${TARGETS[@]}"; do
  install_link "$target"
  if [ "$target" = "claude" ]; then
    install_claude_hook
  elif [ "$target" = "codex" ]; then
    install_codex_hook
  else
    echo "[2] $target: UserPromptSubmit 훅 등록 대상 아님 — skip"
  fi
done

echo "[3] 의존성:  pip install rdflib pyyaml"
echo "[4] 설정:"
echo "      - projects.yaml 에 본인 프로젝트 등록 (projects.example.yaml 복사)"
echo "      - machine.yaml 은 첫 실행 시 .obsidian 자동탐지로 부트스트랩 (또는 machine.example.yaml 복사)"
echo "      - ug use <project> 로 현재 작업 프로젝트 고정 → 신호0 발화도 추론"
echo "완료. 다음 세션부터 매 발화 자동 grounding."

#!/usr/bin/env bash
# check-private.sh — git push 전 개인정보(PII) 스캔. PII 발견 시 exit 1 → push 차단.
# repository/ 는 추후 공개 예정 → 절대경로·이메일·vault 시그니처·사용자 데이터가
# 공개 단위에 새는지 검사한다. 사용: bash check-private.sh [scan-dir]
#   scan-dir 기본 = 이 스크립트가 속한 전체 Git 배포 저장소.
# git-tracked 파일만 검사(= 실제 push 대상). *.example.yaml·체커 자신은 제외.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
DEFAULT_SCAN="$(git -C "$SCRIPT_DIR" rev-parse --show-toplevel 2>/dev/null || echo "$SCRIPT_DIR")"
SCAN="${1:-$DEFAULT_SCAN}"
cd "$SCAN" 2>/dev/null || { echo "[check-private] 경로 없음: $SCAN"; exit 1; }
SELF="$(basename "$0")"
problems=0
note() { echo "  ✗ $1"; problems=$((problems + 1)); }

# 실제 push 대상 = git-tracked. (없으면 find 폴백). bash 3.2 호환 — mapfile 미사용.
files="$(git ls-files 2>/dev/null)"
[ -z "$files" ] && files="$(find . -type f -not -path '*/.git/*')"

while IFS= read -r f; do
  [ -z "$f" ] && continue
  base="$(basename "$f")"
  [ "$base" = "$SELF" ] && continue
  case "$base" in *.example.yaml | *.example.*) continue ;; esac
  [ -f "$f" ] || continue
  case "$base" in
    machine.yaml | .session.json | projects.yaml)
      note "$f: 사용자 데이터가 git 추적됨 — *.example 만 배포"
      ;;
  esac
  if grep -qE 'iCloud~md~obsidian|/Users/[a-z][a-z0-9._-]+' "$f" 2>/dev/null; then
    note "$f: vault 시그니처/실 사용자 홈 절대경로 (placeholder 는 /Users/<you> 사용)"
  fi
  if grep -qE '[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}' "$f" 2>/dev/null; then
    note "$f: 이메일 추정 (값은 출력하지 않음)"
  fi
  if grep -qE 'gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,}|AKIA[A-Z0-9]{16}|sk-(proj-)?[A-Za-z0-9_-]{32,}|-----BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY-----' "$f" 2>/dev/null; then
    note "$f: 자격 증명/개인 키 패턴 (값은 출력하지 않음)"
  fi
done <<EOF
$files
EOF

if [ "$problems" -gt 0 ]; then
  echo "[check-private] PII/유출 $problems 건 발견 — push 금지. 제거·ignore 후 재검사."
  exit 1
fi
echo "[check-private] PASS — 공개 단위에 PII 없음."

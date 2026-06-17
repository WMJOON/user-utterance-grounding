#!/usr/bin/env bash
# check-private.sh — git push 전 개인정보(PII) 스캔. PII 발견 시 exit 1 → push 차단.
# repository/ 는 추후 공개 예정 → 절대경로·이메일·vault 시그니처·사용자 데이터가
# 공개 단위에 새는지 검사한다. 사용: bash check-private.sh [scan-dir]
#   scan-dir 기본 = 이 스크립트가 있는 스킬 디렉토리(공개 단위).
# git-tracked 파일만 검사(= 실제 push 대상). *.example.yaml·체커 자신은 제외.
set -uo pipefail

SCAN="${1:-$(cd "$(dirname "$0")" && pwd)}"
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
  if grep -qE 'iCloud~md~obsidian|/Users/[a-z][a-z0-9._-]+' "$f" 2>/dev/null; then
    note "$f: vault 시그니처/실 사용자 홈 절대경로 (placeholder 는 /Users/<you> 사용)"
  fi
  if grep -qE '[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}' "$f" 2>/dev/null; then
    note "$f: 이메일 추정 ($(grep -oE '[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}' "$f" | head -1))"
  fi
done <<EOF
$files
EOF

# 사용자 데이터가 추적되면 공개 단위에 샌다 → gitignore 필요
for sensitive in machine.yaml .session.json projects.yaml; do
  if git ls-files --error-unmatch "$sensitive" >/dev/null 2>&1; then
    note "$sensitive: 사용자 데이터가 git 추적됨 — gitignore 필요(공개 단위 미포함, *.example 만 배포)"
  fi
done

if [ "$problems" -gt 0 ]; then
  echo "[check-private] PII/유출 $problems 건 발견 — push 금지. 제거·ignore 후 재검사."
  exit 1
fi
echo "[check-private] PASS — 공개 단위에 PII 없음."

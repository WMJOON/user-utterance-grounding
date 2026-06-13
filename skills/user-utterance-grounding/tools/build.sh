#!/usr/bin/env bash
# tools/build.sh — LinkML schema → OWL/SHACL/JSON-schema 파생 (검증용).
# DEV 전용: linkml 필요 (pip install linkml). 런타임(lookup.py)은 이게 없어도 동작.
# MSM 패턴: 엄밀 정의(nlu_intent.yaml + user_intents.ttl) → 컨버팅해서 사용.
set -euo pipefail

SKILL_DIR="$(cd "$(dirname "$0")/.." && pwd)"
SCHEMA="$SKILL_DIR/references/schemas/nlu_intent.yaml"
OUT="$SKILL_DIR/generated"
mkdir -p "$OUT"

command -v gen-owl >/dev/null || { echo "linkml 미설치 — 'pip install linkml' 후 재실행"; exit 1; }

echo "[1/3] gen-owl ...";         gen-owl         "$SCHEMA" > "$OUT/nlu_intent.owl.ttl"
echo "[2/3] gen-shacl ...";       gen-shacl       "$SCHEMA" > "$OUT/nlu_intent.shacl.ttl"
echo "[3/3] gen-json-schema ...";  gen-json-schema "$SCHEMA" > "$OUT/nlu_intent.schema.json"
echo "Build OK — $OUT/"

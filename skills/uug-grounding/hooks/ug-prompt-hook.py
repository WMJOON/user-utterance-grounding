#!/usr/bin/env python3
"""UserPromptSubmit 훅 — 매 발화를 자동 ground 해 타깃 프로젝트를 컨텍스트에 주입.

값-전달 레이어(planning §8-3c): grounding *능력* 을 실제 가치로. UserPromptSubmit 의
plain stdout 은 모델 컨텍스트에 주입된다(검증된 경로). 확신(target 해석)일 때만 1줄
주입하고, 아니면 침묵 → 매 프롬프트 노이즈 방지. 항상 exit 0 (프롬프트 차단 안 함).
이 hook은 기록, dispatch, worklog 생성 side effect를 하지 않는다.

등록(.claude/settings.json 또는 .codex/config.toml):
  "UserPromptSubmit": [{"hooks": [{"type":"command",
     "command":"python3 <path>/hooks/ug-prompt-hook.py"}]}]
의존성: ug.py + lookup.py (rdflib). 미설치/오류 시 조용히 통과.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

UG = Path(__file__).resolve().parent.parent / "scripts" / "ug.py"


def main():
    if os.environ.get("UUG_DISABLED") == "1" or os.environ.get("UUG_ENABLED") == "0":
        return
    if os.environ.get("UUG_HOOKS_DISABLED") == "1":
        return
    try:
        data = json.load(sys.stdin)
    except Exception:
        return
    prompt = (data.get("prompt") or "").strip()
    if not prompt:
        return
    try:
        r = subprocess.run(
            [sys.executable, str(UG), "ground", "--for-hook", prompt],
            capture_output=True, text=True, timeout=10,
        )
    except Exception:
        return
    out = (r.stdout or "").strip()
    if out:
        # UserPromptSubmit: stdout 이 모델 컨텍스트로 주입됨
        print(out)


if __name__ == "__main__":
    main()

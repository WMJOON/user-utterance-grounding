#!/usr/bin/env python3
"""UserPromptSubmit 훅 — 발화가 지칭하는 프로젝트를 매 프롬프트 추론해, 확신할 때 대상과 작업 시작 계약을 주입한다.

`ug.py infer` 를 호출한다 (~0.2s):
  explicit(프로젝트 id·aliases)  → 대상 디렉토리 안내
  tacit(keywords) 한쪽으로 모임   → 추정 대상 + 확인 요청
  tacit 여러 프로젝트로 갈라짐    → clarify 지시 (연속성·유사 발화 기준 추천 표시)
  키워드 없음                    → 연속성(transcript 직전 턴 작업 경로) → 유사 발화 폴백,
                                   둘이 일치하거나 명시적 연속 제어 발화일 때 넛지
모든 판정은 넛지 여부와 무관하게 ~/.local/share/uug/locate-log.jsonl 에 원문 없이 남는다.
같은 디렉토리도 새 작업의 맥락 조회 계약을 전달한다. 항상 exit 0 (프롬프트 차단 안 함).

등록:
  Claude Code  ~/.claude/settings.json  hooks.UserPromptSubmit
               command: python3 "<path>/hooks/ug-locate-hook.py"
  Codex        ~/.codex/config.toml     [features] hooks = true + [[hooks.UserPromptSubmit]]
               command: python3 "<path>/hooks/ug-locate-hook.py" --codex
               (Codex 는 등록 후 대화형 `/hooks` 에서 신뢰 승인해야 실행된다)
끄기: UUG_DISABLED=1 / UUG_ENABLED=0 / UUG_HOOKS_DISABLED=1
"""
import json
import os
import subprocess
import sys
from context_contract import format_context
from pathlib import Path

UG = Path(__file__).resolve().parent.parent / "scripts" / "ug.py"
CODEX = "--codex" in sys.argv[1:]


def _emit(msg):
    """Claude: plain stdout 이 컨텍스트로 주입된다. Codex: additionalContext JSON."""
    if CODEX:
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "UserPromptSubmit",
                                                 "additionalContext": msg}}, ensure_ascii=False))
    else:
        print(msg)


def main():
    if (os.environ.get("UUG_DISABLED") == "1" or os.environ.get("UUG_ENABLED") == "0"
            or os.environ.get("UUG_HOOKS_DISABLED") == "1"):
        return
    try:
        data = json.load(sys.stdin)
    except Exception:
        return
    prompt = (data.get("prompt") or "").strip()
    if not prompt or not UG.exists():
        return
    cwd = os.environ.get("CLAUDE_PROJECT_DIR") or data.get("cwd")
    cmd = [sys.executable, str(UG), "infer", "--log", prompt]
    if data.get("transcript_path"):
        cmd += ["--transcript", data["transcript_path"]]
    if cwd:
        cmd += ["--session-dir", cwd]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=9)
        loc = json.loads(r.stdout) if r.returncode == 0 else None
    except Exception:
        return
    if not loc or not loc.get("emit"):
        return

    msg = format_context(loc, cwd)
    if msg:
        _emit(msg)


if __name__ == "__main__":
    main()

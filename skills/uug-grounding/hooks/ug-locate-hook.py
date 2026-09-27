#!/usr/bin/env python3
"""UserPromptSubmit 훅 — 발화가 지칭하는 프로젝트를 매 프롬프트 추론해, 확신할 때만 1줄 주입한다.

`ug.py infer` 를 호출한다 (~0.2s):
  explicit(프로젝트 id·aliases)  → 대상 디렉토리 안내
  tacit(keywords) 한쪽으로 모임   → 추정 대상 + 확인 요청
  tacit 여러 프로젝트로 갈라짐    → clarify 지시 (연속성·유사 발화 기준 추천 표시)
  키워드 없음                    → 연속성(transcript 직전 턴 작업 경로) → 유사 발화 폴백,
                                   둘이 일치할 때만 넛지
모든 판정은 넛지 여부와 무관하게 ~/.local/share/uug/locate-log.jsonl 에 원문 없이 남는다.
현재 세션 디렉토리와 같은 대상이면 침묵. 항상 exit 0 (프롬프트 차단 안 함).

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


def _same_dir(a, b):
    try:
        return Path(a).resolve() == Path(b).resolve()
    except Exception:
        return False


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

    cands = loc.get("candidates") or []
    if loc["status"] == "clarify":
        opts = " | ".join(
            f"{c['project']}" + (f" {c['share']:.0%}" if c.get("share") else "") + f" ({c['path']})"
            for c in cands)
        rec, by = loc.get("recommended"), loc.get("recommended_by") or "과거 유사 발화"
        hint = f" {by} 기준 '{rec}' 가 유력하니 이를 첫 선택지로 제시하되," if rec else ""
        _emit(f"[uug-locate] '{', '.join(loc['keywords'])}' 은(는) 여러 프로젝트를 지칭할 수 있음: "
              f"{opts} —{hint} 대상을 추측하지 말고 어느 쪽인지 사용자에게 먼저 확인할 것.")
        return
    c = cands[0]
    if not c.get("path") or (cwd and _same_dir(cwd, c["path"])):
        return
    if loc["status"] == "likely":
        _emit(f"[uug-locate] 추정 대상={c['project']} (암묵 키워드 '{c['keyword']}') → {c['path']} "
              f"— 현재 세션 디렉토리와 다름. 이 프로젝트가 맞는지 짧게 확인한 뒤 진행할 것.")
    elif loc["status"] == "inferred":
        _emit(f"[uug-locate] 이어지는 작업 대상={c['project']} ({c['keyword']}) → {c['path']} "
              f"— 현재 세션 디렉토리와 다름. 파일을 찾을 때 이 경로를 우선할 것.")
    else:
        _emit(f"[uug-locate] 지칭 대상={c['project']} ('{c['keyword']}') → {c['path']} "
              f"(현재 세션 디렉토리와 다름 — 이 경로에서 찾을 것)")


if __name__ == "__main__":
    main()

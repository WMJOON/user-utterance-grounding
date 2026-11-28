"""Read-only context delivery shared by installed and repository hooks."""
import hashlib
import json
import os
import time
from pathlib import Path

# 대상 저장소 지침 주입: 작업 대상이 현재 세션 디렉토리와 다르면 그 저장소의 CLAUDE.md(없으면 AGENTS.md)를
# 컨텍스트에 붙인다. 같은 (세션 디렉토리, 대상, 파일 내용) 조합은 TTL 동안 한 번만 주입한다.
RULE_FILES = ("CLAUDE.md", "AGENTS.md")
MAX_CHARS = int(os.environ.get("UUG_TARGET_RULES_MAX_CHARS", "8000"))
TTL_SECONDS = int(os.environ.get("UUG_TARGET_RULES_TTL", "7200"))
STATE = Path(os.environ.get("UUG_TARGET_RULES_STATE",
                            str(Path.home() / ".local" / "share" / "uug" / "target-rules-injected.json")))


def _same(a, b):
    try:
        return Path(a).resolve() == Path(b).resolve()
    except Exception:
        return False


def target_rules(path, cwd=None, now=None):
    """대상 저장소 지침 본문 블록. 주입할 필요가 없으면 None."""
    if os.environ.get("UUG_TARGET_RULES_DISABLED") == "1" or not path:
        return None
    if cwd and _same(cwd, path):
        return None
    rule = next((Path(path) / n for n in RULE_FILES if (Path(path) / n).is_file()), None)
    if rule is None:
        return None
    try:
        text = rule.read_text(encoding="utf-8")
    except Exception:
        return None
    now = now or time.time()
    key = hashlib.sha256(f"{cwd}|{Path(path).resolve()}|{hashlib.sha256(text.encode()).hexdigest()}".encode()).hexdigest()
    try:
        state = json.loads(STATE.read_text(encoding="utf-8"))
    except Exception:
        state = {}
    if now - state.get(key, 0) < TTL_SECONDS:
        return None
    state = {k: v for k, v in state.items() if now - v < TTL_SECONDS}
    state[key] = now
    try:
        STATE.parent.mkdir(parents=True, exist_ok=True)
        STATE.write_text(json.dumps(state), encoding="utf-8")
    except Exception:
        pass
    body = text if len(text) <= MAX_CHARS else text[:MAX_CHARS] + f"\n…(이하 생략, 전문: {rule})"
    return (f"[uug-target-rules] 대상 저장소 지침 {rule} (작업 대상이 현재 세션 디렉토리와 다름. "
            f"이 지침을 이번 작업에 적용할 것)\n<target-rules path=\"{rule}\">\n{body}\n</target-rules>")

def format_context(loc, cwd=None):
    candidates = loc.get("candidates") or []
    if not loc.get("emit") or not candidates:
        return None
    if loc["status"] == "clarify":
        options = " | ".join(f"{c['project']} ({c.get('path')})" for c in candidates)
        rec = loc.get("recommended")
        hint = f" 추천 후보={rec}." if rec else ""
        return f"[uug-locate] 대상 모호: {options}.{hint} 대상을 사용자에게 확인한 뒤 진행할 것."
    c = candidates[0]
    if not c.get("path"):
        return None
    prefix = "추정 대상" if loc["status"] == "likely" else "작업 대상"
    confirm = " 이 프로젝트가 맞는지 먼저 확인할 것." if loc["status"] == "likely" else ""
    return (f"[uug-locate] {prefix}={c['project']} → {c['path']}.{confirm}\n"
            "[uug-context] 새 작업 또는 대상 전환이면 작업 시작 전에 대상 저장소의 AGENTS.md·CLAUDE.md와 "
            "agent-context/work-memory/schema.yaml을 확인하고, 현재 작업 키워드로 관련 결정·이슈·해결·인사이트 "
            "기록을 검색해 원문을 읽을 것. 참조 ID·경로와 적용할 제약을 짧게 보고할 것. "
            "기록이 없거나 조회 실패하면 명시할 것. 같은 작업에서 이미 조회했다면 중복 조회하지 말고 "
            "기존 근거를 재사용하되 상태 변경은 재검증할 것. intent→action은 대상 프로젝트의 지침·스킬을 "
            "따르고 기존 사용자 승인 경계를 유지할 것. 훅 출력만으로 기록 조회·행동 완료를 주장하지 말 것."
            + (("\n" + rules) if (loc["status"] != "likely" and (rules := target_rules(c["path"], cwd))) else ""))

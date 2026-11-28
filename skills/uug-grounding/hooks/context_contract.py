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


# ---- context-repository 슬롯 (맥락) + repository task grounding ----
# 1. repository lexical(저장소 어휘)로 대상이 확정(status=clear)되면 세션의 context-repository 를 그 저장소로 전환한다.
# 2. 매 프롬프트, context-repository 저장소의 tasks[].lexical(작업어)이 발화에 있으면 그 저장소 절차(repository task)로 grounding 한다.
# 3. 작업어가 context-repository 에 없고 다른 저장소 한 곳에만 있으면 전환을 제안한다.
ENV_STATE = Path(os.environ.get("UUG_CONTEXT_REPOSITORY_STATE",
                                str(Path.home() / ".local" / "share" / "uug" / "context-repository.json")))


def session_key(transcript=None, cwd=None):
    return str(transcript or cwd or "default")


def _load_env_state():
    try:
        return json.loads(ENV_STATE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def context_repository(key):
    return _load_env_state().get(key)


def update_context_repository(loc, key, now=None):
    """저장소 어휘로 대상이 확정되면 슬롯을 전환한다. 전환했으면 새 값을 반환한다."""
    if not loc or loc.get("status") != "clear" or not loc.get("emit"):
        return None
    c = (loc.get("candidates") or [{}])[0]
    repo = c.get("project")
    if not repo:
        return None
    state = _load_env_state()
    cur = state.get(key) or {}
    if cur.get("repo") == repo:
        return None
    state[key] = {"repo": repo, "path": c.get("path"), "since": now or time.time(), "by": "repository_trigger"}
    try:
        ENV_STATE.parent.mkdir(parents=True, exist_ok=True)
        ENV_STATE.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass
    return state[key]


def _norm(s):
    return "".join(str(s).split()).lower()


def _match_tasks(utterance, tasks):
    u = _norm(utterance)
    return [t for t in (tasks or []) if any(_norm(w) and _norm(w) in u for w in t.get("lexical") or [])]


def ground_task(utterance, env, projects):
    """context-repository 기준 repository task 를 찾는다. 반환: (kind, repo, tasks) 또는 None."""
    env_repo = (env or {}).get("repo")
    if env_repo:
        hits = _match_tasks(utterance, (projects.get(env_repo) or {}).get("tasks"))
        if hits:
            return ("grounded", env_repo, hits)
    owners = [(name, _match_tasks(utterance, (p or {}).get("tasks")))
              for name, p in (projects or {}).items() if name != env_repo]
    owners = [(n, h) for n, h in owners if h]
    if len(owners) == 1:
        return ("switch", owners[0][0], owners[0][1])
    return None


def format_task(result, env=None):
    if not result:
        return None
    kind, repo, tasks = result
    lines = []
    for t in tasks:
        lines.append(f"- {t.get('id')}: {t.get('procedure')}" + (f" ({t.get('note')})" if t.get("note") else ""))
    if kind == "grounded":
        return (f"[uug-task] context-repository={repo} — 이 발화의 작업어는 이 저장소의 절차를 가리킨다. "
                f"일반 도구로 직접 처리하지 말고 아래 절차를 따를 것.\n" + "\n".join(lines))
    cur = (env or {}).get("repo") or "미설정"
    return (f"[uug-task] 작업어가 현재 context-repository({cur})가 아닌 {repo} 의 절차를 가리킨다. "
            f"{repo} 로 전환할지 사용자에게 확인한 뒤 진행할 것.\n" + "\n".join(lines))

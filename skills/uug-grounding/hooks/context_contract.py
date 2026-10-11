"""Read-only context delivery shared by installed and repository hooks."""

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
            "따르고 기존 사용자 승인 경계를 유지할 것. 훅 출력만으로 기록 조회·행동 완료를 주장하지 말 것.")

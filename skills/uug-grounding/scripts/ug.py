#!/usr/bin/env python3
"""user-utterance-grounding (ug) — intent 기반 project grounding + 머신 이식 리졸버.

명령:
  ug.py ground "<발화>"     # 발화 → 타깃 프로젝트 추론 (project-name 미명시여도). Lv10 keyword
  ug.py resolve <project>   # project → 이 머신의 절대경로 (앵커로 해석)
  ug.py doctor              # 레지스트리 전체 경로 존재 확인 (✓ found / ✗ missing / ⚠ anchor)
  ug.py list                # 등록된 프로젝트

설정 (스킬 디렉토리 옆):
  projects.yaml         싱크됨   — {project: {anchor, rel, intents, keywords, tags}}
  machine.yaml          gitignore — {anchors: {name: 절대경로}}  (머신마다 다름)
  machine.example.yaml  싱크됨   — 새 머신용 템플릿
machine.yaml 없으면 .obsidian 마커를 위로 탐지해 vault 앵커를 자동 부트스트랩.
의존성: pyyaml (stdlib 외).
"""
import os
import sys
import json
import datetime
import argparse
from pathlib import Path

import yaml

SKILL_DIR = Path(__file__).resolve().parent.parent   # scripts/ 의 부모 = 스킬 디렉토리
PROJECTS = SKILL_DIR / "projects.yaml"
MACHINE = SKILL_DIR / "machine.yaml"
# last_project 등 세션 상태 (gitignore, 머신-로컬). UG_SESSION 으로 override (테스트 격리).
SESSION = Path(os.environ.get("UG_SESSION", SKILL_DIR / ".session.json"))


def _load_yaml(p, default):
    try:
        return yaml.safe_load(open(p, encoding="utf-8")) or default
    except FileNotFoundError:
        return default


def _autodetect_vault():
    """스킬 위치(symlink resolve 후)에서 위로 .obsidian 을 탐지 → vault 루트."""
    for cand in [SKILL_DIR, *SKILL_DIR.parents]:
        if (cand / ".obsidian").is_dir():
            return str(cand)
    return None


def load_anchors():
    """앵커(앵커명→절대경로) 해소. vault 앵커는 머신-무관하게 자가복구한다.

    machine.yaml 은 gitignore 지만 vault 가 iCloud 동기화 경로 안이면 머신 간에
    복제되어 절대경로가 오염된다(머신마다 홈 경로 다름). vault 는 코드가 그 안에
    살므로 .obsidian 마커로 런타임 도출이 항상 가능 → 저장값이 이 머신에 실재하지
    않으면 탐지값으로 덮어쓰고, 절대경로를 다시 persist 하지 않아 오염 고리를 끊는다.
    vault 밖 앵커(code/home 등)는 machine.yaml 저장값을 그대로 신뢰한다.
    """
    m = _load_yaml(MACHINE, {})
    anchors = dict((m or {}).get("anchors", {}))
    stored = anchors.get("vault")
    if not stored or not Path(stored).is_dir():
        v = _autodetect_vault()
        if v:
            anchors["vault"] = v
            if stored and stored != v:
                print(f"[self-heal] machine.yaml vault={stored} 이 머신에 없음 "
                      f"→ .obsidian 탐지로 {v} 사용 (machine.yaml 미수정)", file=sys.stderr)
    return anchors


def load_projects():
    return _load_yaml(PROJECTS, {}) or {}


def load_session():
    try:
        return json.loads(SESSION.read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError):
        return {}


def save_session(project):
    SESSION.write_text(
        json.dumps(
            {"last_project": project,
             "updated": datetime.datetime.now(datetime.timezone.utc).isoformat()},
            ensure_ascii=False),
        encoding="utf-8",
    )


def resolve_one(name, projects, anchors):
    p = projects.get(name)
    if not p:
        return None, "unknown-project"
    anchor = p.get("anchor")
    if anchor not in anchors:
        return None, f"anchor-undefined:{anchor}"
    return str(Path(anchors[anchor]) / p.get("rel", "")), None


def cmd_resolve(args):
    path, err = resolve_one(args.project, load_projects(), load_anchors())
    if err:
        print(f"[ERROR] {args.project}: {err}", file=sys.stderr)
        return 1
    print(path)
    return 0


def cmd_doctor(args):
    projects, anchors = load_projects(), load_anchors()
    ok = True
    for name in sorted(projects):
        path, err = resolve_one(name, projects, anchors)
        if err and err.startswith("anchor-undefined"):
            print(f"  ⚠ {name}: {err} — machine.yaml 에 앵커 추가 필요")
            ok = False
        elif path and Path(path).exists():
            print(f"  ✓ {name}: {path}")
        else:
            print(f"  ✗ {name}: {path} — 이 머신에 없음(미클론/이동)")
            ok = False
    return 0 if ok else 1


def _match_project(utterance, projects):
    """projects.yaml 키워드/이름으로 발화에서 프로젝트 후보 점수화 (target_project 슬롯 해석)."""
    utt = utterance.lower()
    scored = []
    for name, p in projects.items():
        terms = [name] + list(p.get("keywords", [])) + list(p.get("tags", []))
        hits = sorted({t for t in terms if str(t).lower() and str(t).lower() in utt})
        if hits:
            scored.append((len(hits), name, hits))
    scored.sort(key=lambda x: (-x[0], x[1]))
    return scored


def build_registries(projects, anchors):
    """user 레지스트리 + projects.yaml 에 `intent_registry` 선언이 있는 프로젝트의
    도메인 레지스트리(예: MSO intents.ttl)를 lookup 에 넘길 spec 리스트로 만든다.
    spec: {path, source_project}. 경로 누락/미존재 프로젝트는 조용히 건너뛴다."""
    sys.path.insert(0, str(SKILL_DIR / "src"))
    import lookup
    regs = [{"path": str(lookup.USER_INTENTS), "source_project": None}]
    for name, p in projects.items():
        rel = p.get("intent_registry")
        if not rel:
            continue
        root, err = resolve_one(name, projects, anchors)
        if err or not root:
            print(f"[uug] intent_registry 선언됐으나 프로젝트 '{name}' 경로 미해소({err}) — 스킵",
                  file=sys.stderr)
            continue
        ttl = Path(root) / rel
        if ttl.exists():
            regs.append({"path": str(ttl), "source_project": name})
        else:
            # 조용한 스킵 금지: 선언된 레지스트리 부재는 경고(개명/이동/drift 탐지).
            print(f"[uug] intent_registry 미존재 — '{name}': {ttl} (도메인 intent 미로드)",
                  file=sys.stderr)
    return regs


def _do_ground(utterance):
    """grounding 계산(출력 없음). dict 반환: status no-intent|ambiguous|incomplete|ok + 부가."""
    sys.path.insert(0, str(SKILL_DIR / "src"))
    import lookup  # rdflib

    projects = load_projects()
    anchors = load_anchors()
    registries = build_registries(projects, anchors)
    m = lookup.match_intent(utterance, registries=registries)
    intent = m["intent"]
    if intent is None:
        return {"status": "no-intent"}
    # commit 정책 (§11.1 비회귀): 도메인 intent(source_project 有)는 동점이어도 top-1 commit
    # — MSO router 의 first-match-wins decisiveness 와 동등(실측 fixture 84% ≥ MSO 80%).
    # user intent 의 동점은 HITL 유지(보수적: 잘못된 프로젝트 추론 방지).
    committed_ambiguous = bool(m["ambiguous"] and intent.get("source_project"))
    if m["ambiguous"] and not intent.get("source_project"):
        return {"status": "ambiguous",
                "candidates": [(iid, h) for iid, sc, h in m["candidates"] if sc == m["score"]]}

    # 도메인 intent(프로젝트 레지스트리 출처)는 target_project 가 출처로 함의된다.
    implied_project = intent.get("source_project")
    proj_cands = _match_project(utterance, projects)
    sess = load_session()
    slots, unfilled = {}, []
    for spec in intent["slot_specs"]:
        nm, pol, req = spec["slot_name"], spec["fill_policy"], spec["required"]
        if nm == "target_project":
            if pol == "default":
                slots[nm] = spec["default_value"]
            else:  # session_context: 발화 프로젝트 키워드 → 없으면 last_project(세션) 폴백
                clear = proj_cands and (len(proj_cands) == 1 or proj_cands[0][0] > proj_cands[1][0])
                slots[nm] = proj_cands[0][1] if clear else sess.get("last_project")
        else:
            slots[nm] = spec["default_value"] if pol == "default" else None  # ask 자유텍스트는 Lv30(후속)
        if req and slots[nm] is None:
            unfilled.append(nm)

    # 도메인 intent: target_project 미해소 시 출처 프로젝트로 채운다.
    tp = slots.get("target_project") or implied_project
    target_path = None
    if tp:
        path, err = resolve_one(tp, projects, load_anchors())
        target_path = path if not err else None
        save_session(tp)   # last_project 갱신 (세션 추적)
    if implied_project and tp == implied_project:
        via = "도메인-intent"
    elif proj_cands and slots.get("target_project") == proj_cands[0][1]:
        via = "발화"
    elif tp:
        via = "last_project"
    else:
        via = None
    return {"status": "incomplete" if unfilled else "ok",
            "intent_id": intent["intent_id"], "verb": intent["verb_concept"],
            "hits": m["hits"], "slots": slots, "unfilled": unfilled,
            "target_project": tp, "target_path": target_path, "target_via": via,
            "source_project": implied_project,  # 도메인 intent 출처(dispatch 라우팅 키). user intent 면 None
            "committed_ambiguous": committed_ambiguous}


def cmd_ground(args):
    """발화 → intent(TTL) 분류 → slot fill(ask/session_context/default) → GroundedCommand."""
    sys.path.insert(0, str(SKILL_DIR / "src"))
    try:
        import lookup  # noqa: F401
    except ImportError:
        if getattr(args, "for_hook", False):
            return 0  # hook 은 절대 프롬프트를 막지 않음
        print("[ERROR] rdflib 필요 — pip install rdflib", file=sys.stderr)
        return 1

    r = _do_ground(args.utterance)

    # ── hook 모드: 확신(target 해석)일 때만 1줄 주입, 아니면 침묵. 항상 exit 0. ──
    if getattr(args, "for_hook", False):
        if r.get("target_project") and r.get("target_path"):
            print(f"[uug-grounding] 발화 추정 → intent={r['intent_id']}, "
                  f"target_project={r['target_project']} ({r['target_via']}). 다르면 프로젝트를 명시하세요.")
        return 0

    # ── 일반(verbose) 모드 ──
    if r["status"] == "no-intent":
        print("[ground] intent 미매칭 → 명시 필요 (HITL)")
        return 2
    if r["status"] == "ambiguous":
        print("[ground] intent 모호(동점) — HITL 필요:")
        for iid, h in r["candidates"]:
            print(f"    {iid} (hits={h})")
        return 2
    print(f"[ground] intent={r['intent_id']} (verb={r['verb']}, hits={r['hits']})")
    for nm, v in r["slots"].items():
        tag = f"  [{r['target_via']}]" if (nm == "target_project" and v) else ""
        print(f"    {nm} = {v if v is not None else '(미충족)'}{tag}")
    if r["unfilled"]:
        print(f"  → reprompt(HITL): 필수 슬롯 미충족 {r['unfilled']}")
        return 2
    if r["target_path"]:
        print(f"    └ target_project 경로: {r['target_path']}")
    print(f"  → GroundedCommand {{intent: {r['intent_id']}, slots: {r['slots']}}}")
    return 0


def dispatch_to_project(r, projects, anchors, utterance):
    """도메인 intent → 출처 프로젝트의 dispatch CLI(뒷단)에 subprocess 위임.

    §11 배선: UUG 가 앞단(utterance→intent)을 끝낸 뒤, intent_id 를 그 프로젝트의
    dispatch 진입점에 넘겨 GroundedCommand(slot→target→validate→turn)를 받는다.
    경계 = 프로세스(subprocess). MSO 등 피호출 프로젝트는 UUG 를 모른다(단방향 의존).

    반환: (grounded_command_dict, None) | (None, err_str).
    dispatch 미선언 프로젝트면 (None, "no-dispatch") — 호출측이 UUG 자체 처리로 폴백.
    """
    proj = r.get("source_project")
    spec = (projects.get(proj) or {}).get("dispatch") if proj else None
    if not spec:
        return None, "no-dispatch"
    if spec.get("kind", "cli") != "cli":
        return None, f"unsupported-dispatch-kind:{spec.get('kind')}"

    root, err = resolve_one(proj, projects, anchors)
    if err or not root:
        return None, f"unresolved-project:{proj}:{err}"
    entry = Path(root) / spec["entry"]
    if not entry.exists():
        return None, f"dispatch-entry-missing:{entry}"

    import subprocess
    cmd = [sys.executable, str(entry), "ground",
           "--intent-id", r["intent_id"], "--utterance", utterance]
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    except subprocess.TimeoutExpired:
        return None, "dispatch-timeout"
    if out.returncode != 0:
        return None, f"dispatch-failed(rc={out.returncode}): {out.stderr.strip()[:200]}"
    try:
        return json.loads(out.stdout), None
    except ValueError:
        return None, f"dispatch-bad-json: {out.stdout.strip()[:200]}"


def cmd_dispatch(args):
    """end-to-end: 발화 → UUG ground(앞단) → 도메인이면 프로젝트 뒷단 CLI 위임 → GroundedCommand.

    user intent(또는 dispatch 미선언 도메인)는 UUG 자체 grounding 결과를 출력한다.
    """
    sys.path.insert(0, str(SKILL_DIR / "src"))
    try:
        import lookup  # noqa: F401
    except ImportError:
        print("[ERROR] rdflib 필요 — pip install rdflib", file=sys.stderr)
        return 1

    r = _do_ground(args.utterance)
    if r["status"] == "no-intent":
        print("[dispatch] intent 미매칭 → 명시 필요 (HITL)")
        return 2
    if r["status"] == "ambiguous":
        print("[dispatch] intent 모호(동점) — HITL 필요:")
        for iid, h in r["candidates"]:
            print(f"    {iid} (hits={h})")
        return 2

    projects, anchors = load_projects(), load_anchors()
    grounded, err = dispatch_to_project(r, projects, anchors, args.utterance)

    if grounded is not None:
        # 도메인 프로젝트 뒷단이 완성한 GroundedCommand
        if args.json:
            print(json.dumps(grounded, ensure_ascii=False))
        else:
            print(f"[dispatch→{r['source_project']}] intent={grounded['intent_id']} "
                  f"target={grounded.get('target_id')} tier={grounded.get('tier')}")
            print(f"    slots = {grounded.get('slots')}")
            if grounded.get("reprompt_needed"):
                print(f"  → reprompt(HITL): {grounded.get('reprompt_slots')}")
                return 2
        return 0

    if err != "no-dispatch":
        # dispatch 선언은 있으나 실패 — 조용히 삼키지 않는다(배선/경로 drift 탐지)
        print(f"[dispatch] 프로젝트 뒷단 위임 실패: {err}", file=sys.stderr)
        return 1

    # dispatch 미선언(user intent 등) → UUG 자체 grounding 결과 출력
    if r["unfilled"]:
        print(f"[dispatch] intent={r['intent_id']} slots={r['slots']} "
              f"→ reprompt(HITL): {r['unfilled']}")
        return 2
    if args.json:
        print(json.dumps({"intent_id": r["intent_id"], "slots": r["slots"],
                          "target_project": r["target_project"], "tier": "UUG-local"},
                         ensure_ascii=False))
    else:
        print(f"[dispatch] intent={r['intent_id']} (UUG-local) slots={r['slots']} "
              f"target_project={r['target_project']}")
    return 0


def cmd_use(args):
    """현재 작업 프로젝트를 명시적으로 고정 (last_project) — 이후 신호0 발화 추론에 사용."""
    if args.project not in load_projects():
        print(f"[ERROR] 미등록 프로젝트: {args.project} (projects.yaml 확인)", file=sys.stderr)
        return 1
    save_session(args.project)
    print(f"[use] last_project = {args.project}")
    return 0


def cmd_list(args):
    sess = load_session()
    if sess.get("last_project"):
        print(f"  (last_project = {sess['last_project']})")
    for name, p in sorted(load_projects().items()):
        print(f"  {name}: {p.get('anchor')}/{p.get('rel')}  keywords={p.get('keywords', [])[:3]}…")
    return 0


def main():
    ap = argparse.ArgumentParser(prog="ug", description="user-utterance-grounding")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("resolve"); s.add_argument("project"); s.set_defaults(func=cmd_resolve)
    s = sub.add_parser("doctor"); s.set_defaults(func=cmd_doctor)
    s = sub.add_parser("ground"); s.add_argument("utterance")
    s.add_argument("--for-hook", action="store_true", help="hook 모드: 확신 시 1줄 주입, 아니면 침묵, 항상 exit 0")
    s.set_defaults(func=cmd_ground)
    s = sub.add_parser("dispatch"); s.add_argument("utterance")
    s.add_argument("--json", action="store_true", help="GroundedCommand 를 JSON 한 줄로 출력")
    s.set_defaults(func=cmd_dispatch)
    s = sub.add_parser("use"); s.add_argument("project"); s.set_defaults(func=cmd_use)
    s = sub.add_parser("list"); s.set_defaults(func=cmd_list)
    args = ap.parse_args()
    sys.exit(args.func(args))


if __name__ == "__main__":
    main()

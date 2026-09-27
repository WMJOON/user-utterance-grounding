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
import socket
from pathlib import Path

import yaml

SKILL_DIR = Path(__file__).resolve().parent.parent   # scripts/ 의 부모 = 스킬 디렉토리
PROJECTS = SKILL_DIR / "projects.yaml"
MACHINE = SKILL_DIR / "machine.yaml"
# last_project 등 세션 상태 (gitignore, 머신-로컬). UG_SESSION 으로 override (테스트 격리).
SESSION = Path(os.environ.get("UG_SESSION", SKILL_DIR / ".session.json"))


def uug_disabled():
    return os.environ.get("UUG_DISABLED") == "1" or os.environ.get("UUG_ENABLED") == "0"


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


def current_host():
    """machine.yaml hosts 섹션 키. UG_HOST 로 override (테스트 격리)."""
    return os.environ.get("UG_HOST") or socket.gethostname().split(".")[0]


def absent_anchors():
    """이 머신 섹션에서 null 로 선언한 앵커명 (= 이 머신에는 없는 프로젝트 루트)."""
    hosts = (_load_yaml(MACHINE, {}) or {}).get("hosts") or {}
    mine = (hosts.get(current_host()) or {}).get("anchors") or {}
    return {a for a, v in mine.items() if v is None}


def load_anchors():
    """앵커(앵커명→절대경로) 해소. vault 앵커는 머신-무관하게 자가복구한다.

    machine.yaml 은 gitignore 지만 vault 가 iCloud 동기화 경로 안이면 머신 간에
    복제되어 절대경로가 오염된다(머신마다 홈 경로 다름). vault 는 코드가 그 안에
    살므로 .obsidian 마커로 런타임 도출이 항상 가능 → 저장값이 이 머신에 실재하지
    않으면 탐지값으로 덮어쓰고, 절대경로를 다시 persist 하지 않아 오염 고리를 끊는다.
    vault 밖 앵커(code/home 등)는 machine.yaml 저장값을 그대로 신뢰한다.
    같은 이유로 vault 밖 앵커는 hosts.<hostname>.anchors 에 머신별로 두고,
    공통 anchors 위에 이 머신 섹션을 덮어쓴다.
    """
    m = _load_yaml(MACHINE, {}) or {}
    anchors = dict(m.get("anchors") or {})
    anchors.update(((m.get("hosts") or {}).get(current_host()) or {}).get("anchors") or {})
    anchors = {k: v for k, v in anchors.items() if v is not None}
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
    elsewhere = absent_anchors()
    ok = True
    print(f"  (host = {current_host()}, python = {sys.executable})")
    try:
        import rdflib  # noqa: F401  ground/dispatch 런타임 의존성
    except ImportError:
        print("  ⚠ rdflib 없음 — ground/dispatch 불가: pip install -r requirements.txt")
        ok = False
    for name in sorted(projects):
        path, err = resolve_one(name, projects, anchors)
        if err and projects[name].get("anchor") in elsewhere:
            print(f"  − {name}: 이 머신에 없음 (hosts 섹션 null, anchor={projects[name]['anchor']})")
        elif err and err.startswith("anchor-undefined"):
            print(f"  ⚠ {name}: {err} — machine.yaml 에 앵커 추가 필요")
            ok = False
        elif path and Path(path).exists():
            print(f"  ✓ {name}: {path}")
        else:
            print(f"  ✗ {name}: {path} — 이 머신에 없음(미클론/이동)")
            ok = False
    return 0 if ok else 1


def _kw_in(kw, utt_lower):
    """키워드 포함 여부. 영숫자 키워드는 더 긴 토큰의 일부면 불일치 ('UUG' ⊄ 'uug-locate').
    한글 등 비ASCII 키워드는 조사가 붙으므로 부분 문자열로 본다."""
    k = str(kw).lower()
    if not k:
        return False
    if not k.isascii():
        return k in utt_lower
    import re
    return re.search(r"(?<![A-Za-z0-9_-])" + re.escape(k) + r"(?![A-Za-z0-9_-])", utt_lower) is not None


def _match_project(utterance, projects):
    """projects.yaml 키워드/이름으로 발화에서 프로젝트 후보 점수화 (target_project 슬롯 해석)."""
    utt = utterance.lower()
    scored = []
    for name, p in projects.items():
        terms = [name] + list(p.get("aliases", [])) + list(p.get("keywords", [])) + list(p.get("tags", []))
        hits = sorted({t for t in terms if _kw_in(t, utt)})
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


# ambiguous fallback 임계: top-2 margin(top-1 − top-2 점수) < 임계 → commit 대신 HITL.
# 기본값은 §11.1 비회귀 —
#   user   1: 동점(margin 0)만 ambiguous (v0.1.0 이전 동작과 동일. 잘못된 프로젝트 추론 방지)
#   domain 0: 동점도 top-1 commit (MSO first-match-wins decisiveness, 실측 fixture 84% ≥ 80%)
# 실측(tests/fixtures/mso_utterances_50.jsonl): 오답은 margin 0 에 집중, margin ≥ 1 은 전건
# 정답 → 기본 임계 상향은 무익. 키워드 가중 스코어링으로 margin 해상도 확보 후 재검토.
AMBIGUOUS_MARGIN_USER = 1
AMBIGUOUS_MARGIN_DOMAIN = 0


def _margin_threshold(is_domain):
    """스코프별 ambiguous 임계. env 로 실험/튜닝 override 가능."""
    var = "UG_AMBIGUOUS_MARGIN_DOMAIN" if is_domain else "UG_AMBIGUOUS_MARGIN_USER"
    default = AMBIGUOUS_MARGIN_DOMAIN if is_domain else AMBIGUOUS_MARGIN_USER
    try:
        return int(os.environ.get(var, default))
    except ValueError:
        return default


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
    margin = m["margin"]
    threshold = _margin_threshold(bool(intent.get("source_project")))
    if margin is not None and margin < threshold:
        # 후보는 임계 창 안(top 점수와의 차 < 임계)만 노출 — 기본 임계 1에선 동점만.
        return {"status": "ambiguous", "margin": margin, "threshold": threshold,
                "candidates": [(iid, sc, h) for iid, sc, h in m["candidates"]
                               if m["score"] - sc < threshold]}
    # 동점(margin 0)인데 commit 된 경우 관측 플래그 — 기본 임계에선 도메인 intent 만 해당
    # (§11.1 first-match-wins). uug-pattern-analytics 의 임계 튜닝 재료.
    committed_low_margin = margin == 0

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
            "margin": margin,
            "committed_low_margin": committed_low_margin}


def cmd_ground(args):
    """발화 → intent(TTL) 분류 → slot fill(ask/session_context/default) → GroundedCommand."""
    if uug_disabled():
        if not getattr(args, "for_hook", False):
            print("[uug] disabled by UUG_DISABLED=1 or UUG_ENABLED=0")
        return 0
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

    # ── json 모드: _do_ground() 결과를 그대로 한 줄 JSON 으로. dispatch_to_project 를
    # 거치지 않는다(도메인 프로젝트 뒷단 위임은 dispatch 전용) — hook 등 intent_id/
    # target_project 만 필요한 소비자가 dispatch 의 nested subprocess 비용 없이 쓰라고 존재.
    if getattr(args, "json", False):
        print(json.dumps(r, ensure_ascii=False))
        return 2 if r["status"] in ("no-intent", "ambiguous") else 0

    # ── 일반(verbose) 모드 ──
    if r["status"] == "no-intent":
        print("[ground] intent 미매칭 → 명시 필요 (HITL)")
        return 2
    if r["status"] == "ambiguous":
        print(f"[ground] intent 모호(top-2 margin={r['margin']} < {r['threshold']}) — HITL 필요:")
        for iid, sc, h in r["candidates"]:
            print(f"    {iid} (score={sc}, hits={h})")
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
    # uug-context-hook.py 등 호출측이 `ug.py dispatch`를 outer timeout=10s로 감싸는 것을
    # 전제로 한다. inner timeout이 outer보다 크면(과거 30s) outer가 SIGTERM으로 강제
    # 종료할 때까지 이 프로세스가 불필요하게 오래 붙잡혀 있어 훅 지연의 원인이 된다.
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=8)
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
    if uug_disabled():
        if args.json:
            print(json.dumps({"status": "disabled", "tier": "UUG-disabled"}, ensure_ascii=False))
        else:
            print("[uug] disabled by UUG_DISABLED=1 or UUG_ENABLED=0")
        return 0
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
        print(f"[dispatch] intent 모호(top-2 margin={r['margin']} < {r['threshold']}) — HITL 필요:")
        for iid, sc, h in r["candidates"]:
            print(f"    {iid} (score={sc}, hits={h})")
        return 2

    projects, anchors = load_projects(), load_anchors()
    grounded, err = dispatch_to_project(r, projects, anchors, args.utterance)

    if grounded is not None:
        # 도메인 프로젝트 뒷단이 완성한 GroundedCommand
        if args.json:
            # UUG 앞단 관측값(margin) 부착 — uug-pattern-analytics 임계 튜닝 재료 (uug_ 접두 additive)
            grounded.setdefault("uug_margin", r["margin"])
            grounded.setdefault("uug_committed_low_margin", r["committed_low_margin"])
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
                          "target_project": r["target_project"], "tier": "UUG-local",
                          "uug_margin": r["margin"],
                          "uug_committed_low_margin": r["committed_low_margin"]},
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


# uug-pattern-analytics 가 태깅 이력으로 학습한 '키워드 → 실제 작업 프로젝트' 분포
KEYWORD_MAP = SKILL_DIR.parent / "uug-pattern-analytics" / "workspace" / "keyword-map.json"


def _resolve_target(name, projects, anchors):
    """등록 프로젝트 또는 '<umbrella>:<sub>'(미등록 서브모듈) → 절대경로."""
    if ":" in name:
        base, sub = name.split(":", 1)
        root, err = resolve_one(base, projects, anchors)
        return str(Path(root) / sub) if not err else None
    path, err = resolve_one(name, projects, anchors)
    return path if not err else None


def _umbrella_subs(projects, anchors):
    """.gitmodules 를 가진 등록 루트의 미등록 서브모듈 → {sub_basename: '<umbrella>:<sub>'}."""
    import re
    roots = {os.path.realpath(p) for n in projects
             for p in [_resolve_target(n, projects, anchors)] if p}
    out = {}
    for name in projects:
        root = _resolve_target(name, projects, anchors)
        gm = Path(root) / ".gitmodules" if root else None
        if gm and gm.exists():
            for rel in re.findall(r"^\s*path\s*=\s*(.+?)\s*$", gm.read_text(encoding="utf-8"), re.M):
                sub = os.path.realpath(os.path.join(root, rel))
                own = os.path.realpath(root)
                # 등록 루트와 같거나 그 안쪽(더 깊은 등록 프로젝트 소속)이면 분리하지 않는다
                if not any(r != own and (sub == r or sub.startswith(r + os.sep)) for r in roots):
                    out[os.path.basename(rel)] = f"{name}:{rel}"
    return out


def do_locate(utterance, use_similar=False):
    """발화가 지칭하는 프로젝트 디렉토리 추론 (intent 무관, 부작용 없음).

    키워드 두 종류 (projects.yaml):
      explicit = 프로젝트 id + aliases — 직접 지칭. 학습 분포와 무관하게 확정.
      tacit    = keywords (+ 미등록 서브모듈 이름은 explicit) — 주제 암시. keyword-map 학습 분포로 판정.
    status:
      clear    — explicit 이 한 프로젝트를 가리킴
      likely   — tacit 만 있고 한쪽으로 모이거나(exclusive) 관측 부족(sparse) → 추정, 확인 후 진행
      clarify  — explicit 끼리 충돌 / tacit 이 여러 프로젝트로 갈라짐(ambiguous) / tacit 추정끼리 충돌
      none     — 지칭 키워드 없음
    """
    projects, anchors = load_projects(), load_anchors()
    try:
        kmap = json.loads(KEYWORD_MAP.read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError):
        kmap = {}
    utt = utterance.lower()
    owner, explicit = {}, set()
    for name, p in projects.items():
        for kw in [name] + list(p.get("aliases", [])):
            owner.setdefault(str(kw), name)
            explicit.add(str(kw))
        for kw in p.get("keywords", []):
            owner.setdefault(str(kw), name)
    for base, label in _umbrella_subs(projects, anchors).items():
        if base not in owner:
            owner[base] = label
            explicit.add(base)

    hits = [kw for kw in owner if _kw_in(kw, utt)]
    # 더 긴 키워드에 포함된 짧은 키워드는 제외 ("콘텐츠 허브" 안의 "콘텐츠")
    hits = [k for k in hits if not any(k != o and k.lower() in o.lower() for o in hits)]
    if not hits:
        return {"status": "none", "keywords": [], "candidates": []}

    sure, likely, unsure = {}, {}, {}
    for kw in hits:
        if kw in explicit:
            sure.setdefault(owner[kw], kw)
            continue
        m = kmap.get(kw) or {}
        if m.get("status") == "ambiguous":
            for c in m["candidates"]:
                unsure.setdefault(c["project"], (kw, c["share"]))
            unsure.setdefault(owner[kw], (kw, 0.0))   # 등록 소유자는 관측이 적어도 후보에 포함
        elif m.get("status") == "exclusive":
            likely.setdefault(m["candidates"][0]["project"], kw)
        else:   # sparse / 미학습 → 등록 소유자 추정
            likely.setdefault(owner[kw], kw)

    def cand(p, kw, share=None):
        return {"project": p, "keyword": kw, "share": share,
                "kind": "explicit" if kw in explicit else "tacit",
                "path": _resolve_target(p, projects, anchors)}

    if len(sure) == 1:
        (p, kw), = sure.items()
        return {"status": "clear", "keywords": hits, "candidates": [cand(p, kw)]}
    if sure:   # explicit 끼리 충돌 (두 프로젝트를 모두 부름)
        return {"status": "clarify", "keywords": hits,
                "candidates": [cand(p, kw) for p, kw in sure.items()]}
    if len(likely) == 1 and not unsure:
        (p, kw), = likely.items()
        return {"status": "likely", "keywords": hits, "candidates": [cand(p, kw)]}
    for p, kw in likely.items():
        unsure.setdefault(p, (kw, 0.0))
    ranked = sorted(unsure.items(), key=lambda x: -x[1][1])
    out = {"status": "clarify", "keywords": hits,
           "candidates": [cand(p, kw, share) for p, (kw, share) in ranked]}
    if use_similar:
        _rank_by_similar(utterance, out)
    return out


SIMILAR_PY = SKILL_DIR.parent / "uug-pattern-analytics" / "scripts" / "similar.py"
UUG_VENV_PY = Path(os.environ.get("UUG_VENV_PY", Path.home() / ".local/share/uug/venv/bin/python"))
# 모호 키워드 발화 LOO 실측: 후보 내 유사 발화 비중 ≥0.6 이면 80% 적중 (무작위 39%).
# 자동 확정이 아니라 clarify 질문의 추천 순서로만 쓴다.
SIMILAR_RECOMMEND = 0.6
SIMILAR_MIN_NEIGHBORS = 2


def _similar(utterance, candidates=None):
    """과거 유사 발화(zvec + omlx 상주 bge-m3, ~0.1s)의 타깃 순위. 실패 시 []."""
    import subprocess
    if not (UUG_VENV_PY.exists() and SIMILAR_PY.exists()):
        return []
    cmd = [str(UUG_VENV_PY), "-W", "ignore", str(SIMILAR_PY), "query", "--json"]
    if candidates:
        cmd += ["--candidates", ",".join(candidates)]
    try:
        r = subprocess.run(cmd + [utterance], capture_output=True, text=True, timeout=8)
        return json.loads(r.stdout).get("ranking") or []
    except Exception:
        return []


def _rank_by_similar(utterance, out):
    """clarify 후보를 과거 유사 발화(zvec, bge-m3)의 타깃 비중으로 재정렬 + 추천 표시.
    venv·색인이 없거나 실패하면 원래 순서 유지."""
    rank = _similar(utterance, [c["project"] for c in out["candidates"]])
    if not rank:
        return
    w = {x["project"]: (x["weight"], x["neighbors"]) for x in rank}
    for c in out["candidates"]:
        c["similar"], c["neighbors"] = w.get(c["project"], (0.0, 0))
    top = max(out["candidates"], key=lambda c: c["similar"])
    # 이웃 1건짜리 100% 는 근거가 아니다 — 최소 2건 이상 모였을 때만 추천하고 맨 앞으로.
    # 추천이 성립하지 않으면 키워드 분포 순서를 유지한다.
    if top["similar"] >= SIMILAR_RECOMMEND and top["neighbors"] >= SIMILAR_MIN_NEIGHBORS:
        out["recommended"] = top["project"]
        out["candidates"].sort(key=lambda c: c is not top)


def _tag_targets():
    import importlib.util
    p = SKILL_DIR.parent / "uug-pattern-analytics" / "scripts" / "tag_targets.py"
    spec = importlib.util.spec_from_file_location("tag_targets", p)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def prev_target(transcript, utterance="", lookback=5):
    """연속성 신호: 대화 기록(transcript_path)에서 직전 턴들의 타깃.
    도구가 건드린 경로(work) 우선, 없으면 그 턴 발화의 explicit 지칭. 현재 발화 턴은 제외."""
    if not transcript or not Path(transcript).exists():
        return None
    try:
        tt = _tag_targets()
        me = sys.modules[__name__]
        roots = tt.project_roots(me)
        subs = tt.submodule_dirs(roots)
        parse = tt._codex_turns if "/.codex/" in str(transcript) else tt._claude_turns
        turns = list(parse(Path(transcript)))
    except Exception:
        return None
    if turns and turns[-1]["text"].strip() == utterance.strip():
        turns = turns[:-1]
    for turn in reversed(turns[-lookback:]):
        w, _, _ = tt.work_signal(turn, roots, subs)
        if w:
            return w
        loc = do_locate(turn["text"])
        if loc["status"] == "clear":
            return loc["candidates"][0]["project"]
    return None


# eval_targets.py LOO 실측(정답 355건): 직전 타깃 79%(커버 90%), 직전→유사발화 폴백 78%(커버 ~100%),
# 유사발화 단독 51%, 리랭커 50%. → 연속성 우선, 유사 발화는 폴백·보강.
def do_infer(utterance, transcript=None):
    """매 프롬프트 추론: explicit/tacit 키워드(do_locate) + 연속성(prev) + 유사 발화(knn).

    emit=True 일 때만 훅이 넛지한다 (신뢰도 높음). 그 외는 기록용.
      clear              explicit 지칭 → 항상 emit
      clarify            tacit 모호/충돌 → emit, 후보에 연속성(우선)·유사 발화로 추천 표시
      likely             tacit 단일 → emit (연속성과 어긋나면 clarify 로 격상)
      inferred           키워드 없음 → prev 와 knn 이 일치하거나, prev 없이 knn 이 강할 때만 emit
    """
    projects, anchors = load_projects(), load_anchors()
    loc = do_locate(utterance)
    prev = prev_target(transcript, utterance)
    out = dict(loc, prev=prev)

    if loc["status"] == "clear":
        out["emit"] = True
        return out

    def cand(p, why):
        return {"project": p, "keyword": why, "share": None, "kind": "context",
                "path": _resolve_target(p, projects, anchors)}

    if loc["status"] == "likely":
        p = loc["candidates"][0]["project"]
        if prev and prev != p:   # 주제 암시와 직전 작업이 어긋남 → 되묻기
            out.update(status="clarify", recommended=prev, recommended_by="연속성",
                       candidates=[cand(prev, "직전 작업")] + loc["candidates"])
        out["emit"] = True
        return out

    if loc["status"] == "clarify":
        names = [c["project"] for c in loc["candidates"]]
        if prev and prev in names:   # 모호 키워드 발화에서 직전 타깃 적중률 92%
            out["recommended"], out["recommended_by"] = prev, "연속성"
            out["candidates"] = sorted(loc["candidates"], key=lambda c: c["project"] != prev)
        else:
            _rank_by_similar(utterance, out)
            if out.get("recommended"):
                out["recommended_by"] = "유사 발화"
        out["emit"] = True
        return out

    # status none — 키워드 없음: 연속성 → 유사 발화 폴백
    rank = _similar(utterance)
    top = rank[0] if rank else None
    knn = top["project"] if top else None
    strong_knn = bool(top and top["weight"] >= SIMILAR_RECOMMEND
                      and top["neighbors"] >= SIMILAR_MIN_NEIGHBORS)
    target = prev or knn
    out.update(knn=knn, knn_weight=top["weight"] if top else None)
    if not target:
        out["emit"] = False
        return out
    why = ("직전 작업+유사 발화" if prev and prev == knn else "직전 작업" if prev else "유사 발화")
    out.update(status="inferred", candidates=[cand(target, why)],
               emit=bool((prev and prev == knn) or (not prev and strong_knn)))
    return out


LOCATE_LOG = Path(os.environ.get("UUG_LOCATE_LOG", Path.home() / ".local/share/uug/locate-log.jsonl"))


def log_infer(r, transcript, session_dir):
    """넛지 여부와 무관하게 판정을 남긴다 (원문 없음 — transcript 참조만). 분석·임계 튜닝용."""
    try:
        LOCATE_LOG.parent.mkdir(parents=True, exist_ok=True)
        c = (r.get("candidates") or [{}])[0]
        rec = {"ts": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
               "transcript": transcript, "session_dir": session_dir,
               "status": r["status"], "emit": r.get("emit"), "target": c.get("project"),
               "why": c.get("keyword"), "prev": r.get("prev"), "knn": r.get("knn"),
               "knn_weight": r.get("knn_weight"), "recommended": r.get("recommended"),
               "keywords": r.get("keywords")}
        with LOCATE_LOG.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception:
        pass


def cmd_infer(args):
    r = do_infer(args.utterance, args.transcript)
    if args.log:
        log_infer(r, args.transcript, args.session_dir)
    print(json.dumps(r, ensure_ascii=False))
    return 0


def cmd_locate(args):
    r = do_locate(args.utterance, use_similar=args.similar)
    if args.json:
        print(json.dumps(r, ensure_ascii=False))
        return 0
    if r["status"] == "none":
        print("[locate] 지칭 키워드 없음")
        return 0
    head = {"clear": "확정 (explicit)", "likely": f"추정 (tacit: {', '.join(r['keywords'])}) — 확인 후 진행"}.get(
        r["status"], f"모호 — 확인 필요 ({', '.join(r['keywords'])})")
    print(f"[locate] {head}")
    for c in r["candidates"]:
        share = f" 키워드 {c['share']:.0%}" if c.get("share") else ""
        sim = f" 유사발화 {c['similar']:.0%}(n={c['neighbors']})" if "similar" in c else ""
        star = " ★추천" if r.get("recommended") == c["project"] else ""
        print(f"  - {c['project']}{share}{sim}{star}  {c['path'] or '(경로 미해소)'}")
    return 0


def main():
    ap = argparse.ArgumentParser(prog="ug", description="user-utterance-grounding")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("resolve"); s.add_argument("project"); s.set_defaults(func=cmd_resolve)
    s = sub.add_parser("doctor"); s.set_defaults(func=cmd_doctor)
    s = sub.add_parser("ground"); s.add_argument("utterance")
    s.add_argument("--for-hook", action="store_true", help="hook 모드: 확신 시 1줄 주입, 아니면 침묵, 항상 exit 0")
    s.add_argument("--json", action="store_true", help="_do_ground() 결과를 JSON 한 줄로 출력 (dispatch_to_project 미경유)")
    s.set_defaults(func=cmd_ground)
    s = sub.add_parser("dispatch"); s.add_argument("utterance")
    s.add_argument("--json", action="store_true", help="GroundedCommand 를 JSON 한 줄로 출력")
    s.set_defaults(func=cmd_dispatch)
    s = sub.add_parser("locate", help="발화가 지칭하는 프로젝트 디렉토리 (모호하면 clarify)")
    s.add_argument("utterance"); s.add_argument("--json", action="store_true")
    s.add_argument("--similar", action="store_true", help="clarify 후보를 유사 발화(zvec)로 재정렬 (~4s)")
    s.set_defaults(func=cmd_locate)
    s = sub.add_parser("infer", help="매 프롬프트 추론: 키워드 + 연속성(transcript) + 유사 발화 → JSON")
    s.add_argument("utterance"); s.add_argument("--transcript")
    s.add_argument("--session-dir"); s.add_argument("--log", action="store_true")
    s.set_defaults(func=cmd_infer)
    s = sub.add_parser("use"); s.add_argument("project"); s.set_defaults(func=cmd_use)
    s = sub.add_parser("list"); s.set_defaults(func=cmd_list)
    args = ap.parse_args()
    sys.exit(args.func(args))


if __name__ == "__main__":
    main()

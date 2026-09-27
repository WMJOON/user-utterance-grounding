#!/usr/bin/env python3
"""tag_targets.py — 트랜스크립트의 사용자 발화마다 타깃 프로젝트를 태깅한다.

두 신호를 합쳐 발화 1건당 1줄을 남긴다.
  - utterance: 발화 시점 grounding (intent 매칭 + projects.yaml 키워드)
  - work:      그 턴에서 도구가 실제로 건드린 경로 → projects.yaml 루트로 역해석
두 신호가 모두 있고 서로 다르면 disagree=true (grounding 오분류·트리거 정련 재료).

발화 원문은 저장하지 않는다(참조만). 원문이 필요하면 ref(file+uuid/line)로 트랜스크립트를 읽는다.
재실행은 idempotent — ref 가 이미 있는 발화는 건너뛴다(--rebuild 로 전체 재생성).

소스:
  claude  ~/.claude/projects/*/*.jsonl
  codex   ~/.codex/sessions/**/*.jsonl

사용:
  python3 tag_targets.py                 # 증분 태깅 → workspace/utterance-targets.jsonl
  python3 tag_targets.py --rebuild
  python3 tag_targets.py --summary       # 태깅 결과 집계만 출력
"""
import argparse
import importlib.util
import json
import os
import re
import sys
from collections import Counter
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parents[1]
UG_DIR = SKILL_DIR.parent / "uug-grounding"
OUT = SKILL_DIR / "workspace" / "utterance-targets.jsonl"

CLAUDE_GLOB = (Path.home() / ".claude" / "projects", "*/*.jsonl")
CODEX_GLOB = (Path.home() / ".codex" / "sessions", "**/*.jsonl")

# 사람이 친 발화가 아닌 user 메시지 (슬래시 명령·훅 주입·인터럽트·지침 주입)
NOISE_PREFIX = ("<command-", "<local-command", "<system-reminder", "[Request interrupted",
                "Caveat:", "# AGENTS.md instructions", "<environment_context", "<user_instructions",
                "<task-notification", "This session is being continued", "<send_user_message")
PATH_RE = re.compile(r"(?<![\w/.-])((?:/|~/)?[\w.@-]+(?:/[\w.@ -]*[\w.@-])+)")
WORK_SHARE = 0.6   # 턴 경로 hit 중 top 프로젝트 비율이 이 이상이면 work 신호 확정


def _load_ug():
    spec = importlib.util.spec_from_file_location("ug", UG_DIR / "scripts" / "ug.py")
    ug = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ug)
    return ug


# ─── 트랜스크립트 → 턴(발화 + 도구 입력 텍스트) ───

def _claude_turns(path):
    turn = None
    for i, line in enumerate(open(path, encoding="utf-8", errors="replace")):
        try:
            d = json.loads(line)
        except ValueError:
            continue
        msg = d.get("message") or {}
        content = msg.get("content")
        if d.get("type") == "user" and isinstance(content, str) and not d.get("isMeta"):
            text = content.strip()
            if not text or text.startswith(NOISE_PREFIX):
                continue
            if turn:
                yield turn
            turn = {"source": "claude", "file": str(path), "ref": d.get("uuid") or f"L{i}",
                    "ts": d.get("timestamp"), "cwd": d.get("cwd"), "text": text, "tool_text": []}
        elif turn and d.get("type") == "assistant" and isinstance(content, list):
            for c in content:
                if c.get("type") == "tool_use":
                    turn["tool_text"].append(json.dumps(c.get("input") or {}, ensure_ascii=False))
    if turn:
        yield turn


def _codex_turns(path):
    turn, cwd = None, None
    for i, line in enumerate(open(path, encoding="utf-8", errors="replace")):
        try:
            d = json.loads(line)
        except ValueError:
            continue
        p = d.get("payload") or {}
        if d.get("type") == "turn_context":
            cwd = p.get("cwd") or cwd
            if turn and not turn["cwd"]:
                turn["cwd"] = cwd
        item = p.get("item") or {}
        if p.get("type") == "item_completed" and item.get("type") == "UserMessage":
            text = " ".join(c.get("text", "") for c in item.get("content") or []).strip()
            if not text or text.startswith(NOISE_PREFIX):
                continue
            if turn:
                yield turn
            turn = {"source": "codex", "file": str(path), "ref": item.get("id") or f"L{i}",
                    "ts": d.get("timestamp"), "cwd": cwd, "text": text, "tool_text": []}
        elif turn and d.get("type") == "response_item" and p.get("type") in (
                "function_call", "custom_tool_call", "local_shell_call"):
            turn["tool_text"].append(str(p.get("input") or p.get("arguments") or p.get("action") or ""))
    if turn:
        yield turn


def iter_turns():
    for (root, pat), fn in ((CLAUDE_GLOB, _claude_turns), (CODEX_GLOB, _codex_turns)):
        if root.is_dir():
            for f in sorted(root.glob(pat)):
                yield from fn(f)


# ─── 신호 ───

def project_roots(ug):
    projects, anchors = ug.load_projects(), ug.load_anchors()
    roots = []
    for name in projects:
        path, err = ug.resolve_one(name, projects, anchors)
        if not err and path:
            roots.append((os.path.realpath(path), name))
    roots.sort(key=lambda x: -len(x[0]))   # 깊은 루트 우선 (umbrella/sub-project > umbrella)
    return roots


def submodule_dirs(roots):
    """.gitmodules 를 가진 엄브렐러 루트 → 하위 서브모듈 절대경로 목록.
    미등록 서브모듈로 들어간 경로가 엄브렐러로 흡수되지 않게 '<umbrella>:<sub>' 로 분리한다."""
    out = []
    for root, name in roots:
        gm = Path(root) / ".gitmodules"
        if gm.exists():
            for rel in re.findall(r"^\s*path\s*=\s*(.+?)\s*$", gm.read_text(encoding="utf-8"), re.M):
                sub = os.path.realpath(os.path.join(root, rel))
                # 등록 루트와 같거나 그 안쪽(더 깊은 등록 프로젝트 소속)이면 분리하지 않는다
                if not any(r != root and (sub == r or sub.startswith(r + os.sep)) for r, _ in roots):
                    out.append((sub, f"{name}:{rel}"))
    return out


CD_RE = re.compile(r"(?:^|&&|;|\n)\s*cd\s+(\"[^\"]+\"|'[^']+'|\S+)")
_exists = {}


def _real(p):
    if p not in _exists:
        _exists[p] = os.path.realpath(p) if os.path.exists(p) else None
    return _exists[p]


def work_signal(turn, roots, subs=()):
    """턴의 도구 입력에서 경로를 뽑아 가장 깊은 프로젝트 루트로 귀속.
    상대경로는 명령 안의 `cd` 를 따라 해석하고, 실제로 존재하는 경로만 센다."""
    hits = Counter()
    owners = sorted(list(roots) + list(subs), key=lambda x: -len(x[0]))
    for blob in turn["tool_text"]:
        blob = blob.replace("\\n", "\n")
        base = turn.get("cwd")
        cds = CD_RE.findall(blob)
        if cds:
            d = os.path.expanduser(cds[-1].strip("\"'"))
            base = d if os.path.isabs(d) else (os.path.join(base, d) if base else None)
        for raw in set(PATH_RE.findall(blob)):
            p = os.path.expanduser(raw)
            if not os.path.isabs(p):
                if not base:
                    continue
                p = os.path.join(base, p)
            p = _real(os.path.normpath(p))
            if not p:
                continue
            for root, name in owners:
                if p == root or p.startswith(root + os.sep):
                    hits[name] += 1
                    break
    if not hits:
        return None, 0.0, {}
    top, n = hits.most_common(1)[0]
    share = n / sum(hits.values())
    return (top if share >= WORK_SHARE else None), round(share, 2), dict(hits)


def utterance_signal(ug, lookup, registries, projects, text):
    m = lookup.match_intent(text, registries=registries)
    intent = m["intent"]
    cands = ug._match_project(text, projects)
    clear = cands and (len(cands) == 1 or cands[0][0] > cands[1][0])
    target = cands[0][1] if clear else None
    if not target and intent and intent.get("source_project"):
        target = intent["source_project"]   # 도메인 intent 는 출처 프로젝트를 함의
    return {"intent": intent["intent_id"] if intent else None,
            "intent_ambiguous": bool(m.get("ambiguous")),
            "target": target,
            "keyword_hits": cands[0][2] if clear else [],
            # 승자와 무관하게 발화에 등장한 모든 레지스트리 키워드 (keyword-map 학습 재료)
            "keywords": sorted({h for _, _, hits in cands for h in hits})}


def cwd_project(cwd, roots):
    if not cwd:
        return None
    c = os.path.realpath(cwd)
    return next((n for r, n in roots if c == r or c.startswith(r + os.sep)), None)


def tag(turn, ug, lookup, registries, projects, roots, subs=()):
    u = utterance_signal(ug, lookup, registries, projects, turn["text"])
    low = turn["text"].lower()
    # 미등록 서브모듈 이름도 발화 키워드로 취급
    u["keywords"] = sorted(set(u["keywords"]) | {
        os.path.basename(p) for p, _ in subs if os.path.basename(p).lower() in low})
    w_target, w_share, w_hits = work_signal(turn, roots, subs)
    if u["target"] and w_target:
        target, via = w_target, "utterance+work" if u["target"] == w_target else "work"
    elif w_target:
        target, via = w_target, "work"
    elif u["target"]:
        target, via = u["target"], "utterance"
    else:
        target, via = None, None
    return {
        "ref": {"source": turn["source"], "file": turn["file"], "id": turn["ref"]},
        "ts": turn["ts"],
        "cwd_project": cwd_project(turn.get("cwd"), roots),
        "intent": u["intent"], "intent_ambiguous": u["intent_ambiguous"],
        "utterance_target": u["target"], "keyword_hits": u["keyword_hits"],
        "keywords": u["keywords"],
        "work_target": w_target, "work_share": w_share, "work_hits": w_hits,
        "target": target, "target_via": via,
        "disagree": bool(u["target"] and w_target and u["target"] != w_target),
        "len": len(turn["text"]),
    }


def summarize(rows):
    n = len(rows)
    if not n:
        print("[tag] 기록 없음")
        return
    tagged = [r for r in rows if r["target"]]
    print(f"발화 {n}건 · 타깃 확정 {len(tagged)}건 ({len(tagged) / n:.0%})")
    print("  via:", dict(Counter(r["target_via"] or "미확정" for r in rows)))
    print("  intent 매칭:", f"{sum(1 for r in rows if r['intent']) / n:.0%}")
    print("  타깃 분포:")
    for t, c in Counter(r["target"] for r in tagged).most_common():
        print(f"    {c:5d}  {t}")
    dis = [r for r in rows if r["disagree"]]
    print(f"  발화↔작업 불일치 {len(dis)}건:",
          dict(Counter(f"{r['utterance_target']}→{r['work_target']}" for r in dis).most_common(8)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rebuild", action="store_true")
    ap.add_argument("--summary", action="store_true")
    args = ap.parse_args()

    if args.summary:
        rows = [json.loads(l) for l in OUT.open(encoding="utf-8")] if OUT.exists() else []
        summarize(rows)
        return 0

    ug = _load_ug()
    sys.path.insert(0, str(UG_DIR / "src"))
    try:
        import lookup
    except ImportError:
        print("[ERROR] uug-grounding/src/lookup.py(rdflib) 필요", file=sys.stderr)
        return 1
    projects = ug.load_projects()
    registries = ug.build_registries(projects, ug.load_anchors())
    roots = project_roots(ug)
    subs = submodule_dirs(roots)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    seen = set()
    if OUT.exists() and not args.rebuild:
        for line in OUT.open(encoding="utf-8"):
            ref = json.loads(line)["ref"]
            seen.add((ref["file"], ref["id"]))

    new = []
    for turn in iter_turns():
        if (turn["file"], turn["ref"]) in seen:
            continue
        new.append(tag(turn, ug, lookup, registries, projects, roots, subs))

    with OUT.open("w" if args.rebuild else "a", encoding="utf-8") as f:
        for r in new:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"[tag] 신규 {len(new)}건 → {OUT}")
    if new:
        summarize(new)
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Build/query UUG task-rail preference projections.

UUG keeps this projection JSONL-first. MSO workflow TTL may be read to detect
workflow/node drift, but UUG does not mutate MSO task rails or slot specs.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from rdflib import Graph, Namespace, RDF


WF = Namespace("https://mso.dev/ontology/workflow#")
GRAPH_DIR = "graph"
PREFERENCES_JSONL = "task-rail-preferences.jsonl"
DRIFT_JSONL = "task-rail-drift.jsonl"


@dataclass
class Project:
    name: str
    root: Path | None
    keywords: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)


@dataclass
class Preference:
    intent: str
    project: str
    workflow: str = ""
    node: str = ""
    edge: str = ""
    count: int = 0
    last_used_at: str = ""
    sources: set[str] = field(default_factory=set)
    observed_entity_filling: dict[str, dict[str, int]] = field(default_factory=dict)
    adjusted_entity_filling: dict[str, Any] = field(default_factory=dict)
    decision_drift_status: str = "unknown"
    bias_correction_status: str = "unreviewed"


def load_json_maybe(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if not isinstance(value, str) or not value.strip():
        return {}
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as fh:
        for line_no, line in enumerate(fh, 1):
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise SystemExit(f"{path}:{line_no}: invalid JSONL: {exc}") from exc
            if isinstance(row, dict):
                rows.append(row)
    return rows


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def detect_vault_root(start: Path) -> Path | None:
    cur = start.resolve()
    for parent in [cur, *cur.parents]:
        if (parent / ".obsidian").exists():
            return parent
    return None


def load_projects(projects_path: Path) -> dict[str, Project]:
    data = yaml.safe_load(projects_path.read_text(encoding="utf-8")) or {}
    raw_projects = data.get("projects", data)
    if not isinstance(raw_projects, dict):
        return {}

    machine_path = projects_path.with_name("machine.yaml")
    machine = yaml.safe_load(machine_path.read_text(encoding="utf-8")) if machine_path.exists() else {}
    anchors = (machine or {}).get("anchors", {})
    if not isinstance(anchors, dict):
        anchors = {}
    vault = detect_vault_root(projects_path.parent)
    if vault:
        anchors.setdefault("vault", str(vault))

    projects: dict[str, Project] = {}
    for name, spec in raw_projects.items():
        if not isinstance(spec, dict):
            continue
        anchor = spec.get("anchor")
        rel = spec.get("rel", ".")
        root: Path | None = None
        if anchor in anchors:
            root = (Path(str(anchors[anchor])).expanduser() / str(rel)).resolve()
        elif Path(str(rel)).is_absolute():
            root = Path(str(rel)).expanduser().resolve()
        projects[str(name)] = Project(
            name=str(name),
            root=root,
            keywords=[str(v) for v in spec.get("keywords", []) if str(v).strip()],
            tags=[str(v) for v in spec.get("tags", []) if str(v).strip()],
        )
    return projects


def infer_project(row: dict[str, Any], projects: dict[str, Project]) -> str:
    direct = row.get("target_project") or row.get("resolved_target_project") or row.get("project")
    if direct:
        return str(direct)
    if len(projects) == 1:
        return next(iter(projects))
    utterance = str(row.get("utterance", "")).lower()
    best: tuple[int, str] | None = None
    for name, project in projects.items():
        score = sum(1 for signal in [name, *project.keywords, *project.tags] if signal and signal.lower() in utterance)
        if score and (best is None or score > best[0]):
            best = (score, name)
    return best[1] if best else "unknown"


def pick_field(row: dict[str, Any], slots: dict[str, Any], names: list[str]) -> str:
    for name in names:
        if row.get(name):
            return str(row[name])
        if slots.get(name):
            return str(slots[name])
    return ""


def scalar_slot_values(slots: dict[str, Any]) -> dict[str, str]:
    excluded = {
        "workflow",
        "workflow_id",
        "preferred_workflow",
        "node",
        "node_id",
        "workflow_node",
        "preferred_node",
        "edge",
        "edge_id",
        "workflow_edge",
        "preferred_edge",
    }
    values: dict[str, str] = {}
    for key, value in slots.items():
        if key in excluded or value in (None, ""):
            continue
        if isinstance(value, (str, int, float, bool)):
            values[str(key)] = str(value)
    return values


def add_pref(
    prefs: dict[tuple[str, str, str, str, str], Preference],
    *,
    intent: str,
    project: str,
    workflow: str,
    node: str,
    edge: str,
    timestamp: str,
    source: str,
    weight: int = 1,
    observed_entity_filling: dict[str, str] | None = None,
    adjusted_entity_filling: dict[str, Any] | None = None,
    decision_drift_status: str = "",
    bias_correction_status: str = "",
) -> None:
    key = (intent, project, workflow, node, edge)
    pref = prefs.setdefault(key, Preference(intent=intent, project=project, workflow=workflow, node=node, edge=edge))
    pref.count += weight
    if timestamp and timestamp > pref.last_used_at:
        pref.last_used_at = timestamp
    if source:
        pref.sources.add(source)
    for slot_name, entity_value in (observed_entity_filling or {}).items():
        counts = pref.observed_entity_filling.setdefault(slot_name, {})
        counts[entity_value] = counts.get(entity_value, 0) + weight
    if adjusted_entity_filling:
        pref.adjusted_entity_filling.update(adjusted_entity_filling)
    if decision_drift_status:
        pref.decision_drift_status = decision_drift_status
    if bias_correction_status:
        pref.bias_correction_status = bias_correction_status


def collect_from_turns(turns_path: Path, projects: dict[str, Project], prefs: dict[tuple[str, str, str, str, str], Preference]) -> None:
    for row in read_jsonl(turns_path):
        if row.get("type") not in (None, "turn"):
            continue
        intent = row.get("resolved_intent_id") or row.get("intent_id") or row.get("intent")
        if not intent:
            continue
        slots = load_json_maybe(row.get("slots_filled") or row.get("slots"))
        add_pref(
            prefs,
            intent=str(intent),
            project=infer_project(row, projects),
            workflow=pick_field(row, slots, ["workflow", "workflow_id", "preferred_workflow"]),
            node=pick_field(row, slots, ["node", "node_id", "workflow_node", "preferred_node"]),
            edge=pick_field(row, slots, ["edge", "edge_id", "workflow_edge", "preferred_edge"]),
            timestamp=str(row.get("timestamp") or row.get("created_at") or ""),
            source=str(row.get("turn_id") or row.get("id") or ""),
            observed_entity_filling=scalar_slot_values(slots),
        )


def collect_from_memory(user_memory: Path, prefs: dict[tuple[str, str, str, str, str], Preference]) -> None:
    for dirname in ("context", "pattern", "preference"):
        for path in sorted((user_memory / dirname).glob("*.jsonl")):
            for row in read_jsonl(path):
                metadata = load_json_maybe(row.get("metadata"))
                intent = metadata.get("intent") or metadata.get("intent_id") or row.get("intent")
                project = metadata.get("target_project") or metadata.get("project") or row.get("target_project")
                if not intent or not project:
                    continue
                observed = load_json_maybe(metadata.get("observed_entity_filling") or metadata.get("entity_filling"))
                adjusted = load_json_maybe(metadata.get("adjusted_entity_filling") or metadata.get("preferred_entity_filling"))
                add_pref(
                    prefs,
                    intent=str(intent),
                    project=str(project),
                    workflow=str(metadata.get("workflow") or metadata.get("workflow_id") or metadata.get("preferred_workflow") or ""),
                    node=str(metadata.get("node") or metadata.get("node_id") or metadata.get("workflow_node") or metadata.get("preferred_node") or ""),
                    edge=str(metadata.get("edge") or metadata.get("edge_id") or metadata.get("workflow_edge") or metadata.get("preferred_edge") or ""),
                    timestamp=str(row.get("created_at") or metadata.get("last_used_at") or ""),
                    source=str(row.get("id") or path.stem),
                    weight=max(int(metadata.get("usage_count") or metadata.get("weight") or 1), 1),
                    observed_entity_filling={str(k): str(v) for k, v in observed.items()},
                    adjusted_entity_filling=adjusted,
                    decision_drift_status=str(metadata.get("decision_drift_status") or ""),
                    bias_correction_status=str(metadata.get("bias_correction_status") or ""),
                )


def stable_id(prefix: str, parts: list[str]) -> str:
    digest = hashlib.sha1("\x1f".join(parts).encode("utf-8")).hexdigest()[:16]
    return f"{prefix}-{digest}"


def graph_path(user_memory: Path) -> Path:
    return user_memory / GRAPH_DIR / PREFERENCES_JSONL


def preference_record(pref: Preference) -> dict[str, Any]:
    pref_id = stable_id("TRP", [pref.intent, pref.project, pref.workflow, pref.node, pref.edge])
    record = {
        "record_type": "task_rail_preference",
        "id": pref_id,
        "repository": {
            "id": stable_id("UR", [pref.project]),
            "repository_id": pref.project,
            "repository_kind": "mso-enabled",
        },
        "intent": pref.intent,
        "rail": {"workflow": pref.workflow, "node": pref.node, "edge": pref.edge},
        "usage_count": pref.count,
        "last_used_at": pref.last_used_at,
        "derived_from": sorted(pref.sources),
        "observed_entity_filling": pref.observed_entity_filling,
        "adjusted_entity_filling": pref.adjusted_entity_filling,
        "slot_adjustments": [],
        "proposal_mode": "entity-filling-proposal",
        "decision_drift_status": pref.decision_drift_status,
        "bias_correction_status": pref.bias_correction_status,
        "drift_status": "unknown",
    }
    for slot_name, adjusted_value in sorted(pref.adjusted_entity_filling.items()):
        record["slot_adjustments"].append(
            {
                "id": stable_id("SFA", [pref_id, str(slot_name)]),
                "slot_name": str(slot_name),
                "adjusted_value": adjusted_value,
                "adjustment_scope": "node" if pref.node else "edge" if pref.edge else "rail",
                "target_node": pref.node,
                "target_edge": pref.edge,
                "observed_value_distribution": pref.observed_entity_filling.get(str(slot_name), {}),
            }
        )
    return record


def serialize_preferences(user_memory: Path, prefs: dict[tuple[str, str, str, str, str], Preference]) -> Path:
    out = graph_path(user_memory)
    rows = [
        preference_record(pref)
        for pref in sorted(prefs.values(), key=lambda p: (-p.count, p.intent, p.project, p.workflow, p.node, p.edge))
    ]
    write_jsonl(out, rows)
    return out


def cmd_build(args: argparse.Namespace) -> int:
    projects = load_projects(args.projects)
    prefs: dict[tuple[str, str, str, str, str], Preference] = {}
    collect_from_turns(args.turns, projects, prefs)
    collect_from_memory(args.user_memory, prefs)
    print(serialize_preferences(args.user_memory, prefs))
    return 0


def query_rows(rows: list[dict[str, Any]], *, intent: str, project: str | None = None) -> list[dict[str, Any]]:
    filtered = []
    for row in rows:
        if row.get("intent") != intent:
            continue
        if project and row.get("repository", {}).get("repository_id") != project:
            continue
        filtered.append(row)
    filtered.sort(
        key=lambda row: (
            -int(row.get("usage_count") or 0),
            row.get("last_used_at") or "",
            row.get("repository", {}).get("repository_id") or "",
        )
    )
    return filtered


def compact_query_row(row: dict[str, Any]) -> dict[str, Any]:
    rail = row.get("rail", {})
    repository = row.get("repository", {})
    return {
        "preference": row.get("id", ""),
        "intent": row.get("intent", ""),
        "target_project": repository.get("repository_id", ""),
        "workflow": rail.get("workflow", ""),
        "node": rail.get("node", ""),
        "edge": rail.get("edge", ""),
        "usage_count": int(row.get("usage_count") or 0),
        "last_used_at": row.get("last_used_at", ""),
        "drift_status": row.get("drift_status", ""),
        "observed_entity_filling": row.get("observed_entity_filling", {}),
        "adjusted_entity_filling": row.get("adjusted_entity_filling", {}),
        "slot_adjustments": row.get("slot_adjustments", []),
        "proposal_mode": row.get("proposal_mode", ""),
        "decision_drift_status": row.get("decision_drift_status", ""),
        "bias_correction_status": row.get("bias_correction_status", ""),
    }


def cmd_query(args: argparse.Namespace) -> int:
    path = graph_path(args.user_memory)
    if not path.exists():
        raise SystemExit(f"missing projection: {path}")
    for row in query_rows(read_jsonl(path), intent=args.intent, project=args.project):
        print(json.dumps(compact_query_row(row), ensure_ascii=False, sort_keys=True))
    return 0


def workflow_ttls(project_root: Path | None) -> list[Path]:
    if not project_root:
        return []
    candidates = []
    workflow_root = project_root / "agent-context" / "workflow"
    if workflow_root.exists():
        candidates.extend(workflow_root.rglob("*.ttl"))
    candidates.extend(project_root.glob("**/*.abox.ttl"))
    return sorted(set(candidates))


def local_matches(value: str, candidate: str) -> bool:
    if not value:
        return True
    normalized = value.strip().rstrip("/")
    cand = candidate.strip().rstrip("/")
    return cand == normalized or cand.endswith("/" + normalized) or cand.endswith("#" + normalized)


def parse_workflow_index(project_root: Path | None) -> tuple[set[str], set[str]]:
    workflows: set[str] = set()
    nodes: set[str] = set()
    for path in workflow_ttls(project_root):
        graph = Graph()
        try:
            graph.parse(path)
        except Exception:
            continue
        for subject in graph.subjects(RDF.type, WF.Workflow):
            workflows.add(str(subject))
        for rdf_type in (WF.Node, WF.Step, WF.Task):
            for subject in graph.subjects(RDF.type, rdf_type):
                nodes.add(str(subject))
    return workflows, nodes


def drift_for(row: dict[str, Any], projects: dict[str, Project]) -> str:
    repository_id = str(row.get("repository", {}).get("repository_id") or "")
    project = projects.get(repository_id)
    workflows, nodes = parse_workflow_index(project.root if project else None)
    rail = row.get("rail", {})
    workflow = str(rail.get("workflow") or "")
    node = str(rail.get("node") or "")
    if workflow and not any(local_matches(workflow, candidate) for candidate in workflows):
        workflow_path_ok = bool(project and project.root and (project.root / workflow).exists())
        if not workflow_path_ok:
            return "workflow_missing"
    if node and not any(local_matches(node, candidate) for candidate in nodes):
        return "node_missing"
    return "ok"


def cmd_drift(args: argparse.Namespace) -> int:
    projects = load_projects(args.projects)
    path = graph_path(args.user_memory)
    if not path.exists():
        raise SystemExit(f"missing projection: {path}")
    rows = read_jsonl(path)
    drift_rows = []
    for row in rows:
        status = drift_for(row, projects)
        row["drift_status"] = status
        rail = row.get("rail", {})
        drift_rows.append(
            {
                "preference": row.get("id", ""),
                "intent": row.get("intent", ""),
                "target_project": row.get("repository", {}).get("repository_id", ""),
                "workflow": rail.get("workflow", ""),
                "node": rail.get("node", ""),
                "edge": rail.get("edge", ""),
                "status": status,
            }
        )
    write_jsonl(path, rows)
    out = args.user_memory / GRAPH_DIR / DRIFT_JSONL
    drift_rows.sort(key=lambda item: (item["target_project"], item["intent"], item["workflow"], item["node"], item["edge"]))
    write_jsonl(out, drift_rows)
    print(out)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    build = sub.add_parser("build", help="build task-rail preference JSONL from turns and user-memory")
    build.add_argument("--user-memory", type=Path, required=True)
    build.add_argument("--projects", type=Path, required=True)
    build.add_argument("--turns", type=Path, default=Path("workspace/.mso-context/conversation/turns.jsonl"))
    build.set_defaults(func=cmd_build)

    query = sub.add_parser("query", help="query preferred rails by intent")
    query.add_argument("--user-memory", type=Path, required=True)
    query.add_argument("--intent", required=True)
    query.add_argument("--project")
    query.set_defaults(func=cmd_query)

    drift = sub.add_parser("drift", help="detect workflow/node reference drift")
    drift.add_argument("--user-memory", type=Path, required=True)
    drift.add_argument("--projects", type=Path, required=True)
    drift.set_defaults(func=cmd_drift)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())

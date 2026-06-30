import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skills" / "uug-user-memory" / "scripts" / "task_rail_projection.py"


def run_projection(args, *, cwd=ROOT):
    return subprocess.run(
        [sys.executable, str(SCRIPT), *map(str, args)],
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=15,
    )


def write_project_fixture(tmp_path: Path, *, include_workflow=True, include_node=True):
    project_root = tmp_path / "demo-project"
    workflow_root = project_root / "agent-context" / "workflow"
    workflow_root.mkdir(parents=True)
    if include_workflow:
        node_line = ""
        if include_node:
            node_line = """
<https://example.test/node/retry_failed_ticket> a wf:Node ;
  wf:inWorkflow <https://example.test/workflow/main> .
"""
        (workflow_root / "root.abox.ttl").write_text(
            f"""@prefix wf: <https://mso.dev/ontology/workflow#> .

<https://example.test/workflow/main> a wf:Workflow .
{node_line}
""",
            encoding="utf-8",
        )

    (tmp_path / "machine.yaml").write_text(
        f"anchors:\n  tmp: {json.dumps(str(tmp_path))}\n",
        encoding="utf-8",
    )
    projects = tmp_path / "projects.yaml"
    projects.write_text(
        """projects:
  demo:
    anchor: tmp
    rel: demo-project
    keywords: [demo]
    tags: [uug-test]
""",
        encoding="utf-8",
    )
    return projects, project_root


def write_user_memory(tmp_path: Path) -> Path:
    user_memory = tmp_path / "user-memory"
    for dirname in ("context", "pattern", "preference", "graph"):
        (user_memory / dirname).mkdir(parents=True)
    return user_memory


def write_turns(tmp_path: Path, *, count=2, workflow="main", node="retry_failed_ticket") -> Path:
    turns = tmp_path / "turns.jsonl"
    rows = [
        {
            "type": "turn",
            "turn_id": f"turn-{idx}",
            "timestamp": f"2026-06-30T00:00:0{idx}Z",
            "utterance": "demo ticket retry",
            "resolved_intent_id": "dispatch_ticket",
            "target_project": "demo",
            "workflow_id": workflow,
            "workflow_node": node,
            "slots_filled": json.dumps({"ticket_ref": "ticket-217", "reason": "manual_retry"}),
            "success": True,
        }
        for idx in range(count)
    ]
    turns.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    return turns


def parse_jsonl(text: str):
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def test_build_jsonl_from_turns_and_query_sorts_by_usage_count(tmp_path):
    user_memory = write_user_memory(tmp_path)
    projects, _ = write_project_fixture(tmp_path)
    turns = write_turns(tmp_path, count=2)
    extra = tmp_path / "extra-turns.jsonl"
    extra.write_text(
        json.dumps(
            {
                "type": "turn",
                "turn_id": "turn-low",
                "timestamp": "2026-06-30T00:00:09Z",
                "resolved_intent_id": "dispatch_ticket",
                "target_project": "demo",
                "workflow_id": "main",
                "workflow_node": "less_used_node",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    turns.write_text(turns.read_text(encoding="utf-8") + extra.read_text(encoding="utf-8"), encoding="utf-8")

    build = run_projection(["build", "--user-memory", user_memory, "--projects", projects, "--turns", turns])
    assert build.returncode == 0, build.stderr

    projection_path = user_memory / "graph" / "task-rail-preferences.jsonl"
    assert projection_path.exists()
    projection_rows = parse_jsonl(projection_path.read_text(encoding="utf-8"))
    assert projection_rows[0]["record_type"] == "task_rail_preference"
    assert projection_rows[0]["intent"] == "dispatch_ticket"
    assert projection_rows[0]["usage_count"] == 2
    assert projection_rows[0]["repository"]["repository_id"] == "demo"
    assert projection_rows[0]["repository"]["repository_kind"] == "mso-enabled"

    query = run_projection(["query", "--user-memory", user_memory, "--intent", "dispatch_ticket"])
    assert query.returncode == 0, query.stderr
    rows = parse_jsonl(query.stdout)
    assert rows[0]["usage_count"] == 2
    assert rows[0]["node"] == "retry_failed_ticket"
    assert rows[0]["proposal_mode"] == "entity-filling-proposal"
    assert rows[0]["observed_entity_filling"]["ticket_ref"]["ticket-217"] == 2
    assert rows[1]["usage_count"] == 1


def test_memory_metadata_reinforces_count_and_provenance(tmp_path):
    user_memory = write_user_memory(tmp_path)
    projects, _ = write_project_fixture(tmp_path)
    turns = write_turns(tmp_path, count=1)
    (user_memory / "preference" / "UF-0001.jsonl").write_text(
        json.dumps(
            {
                "id": "UF-0001",
                "type": "user-preference",
                "title": "ticket retry rail",
                "text": "Use the retry node for dispatch_ticket",
                "tags": ["task-rail"],
                "created_at": "2026-06-30T00:01:00Z",
                "metadata": {
                    "intent": "dispatch_ticket",
                    "target_project": "demo",
                    "workflow": "main",
                    "node": "retry_failed_ticket",
                    "usage_count": 3,
                    "adjusted_entity_filling": {"reason": "user_preferred_retry"},
                    "decision_drift_status": "stable",
                    "bias_correction_status": "reviewed",
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )

    build = run_projection(["build", "--user-memory", user_memory, "--projects", projects, "--turns", turns])
    assert build.returncode == 0, build.stderr

    rows = parse_jsonl((user_memory / "graph" / "task-rail-preferences.jsonl").read_text(encoding="utf-8"))
    row = rows[0]
    assert row["usage_count"] == 4
    assert "UF-0001" in row["derived_from"]
    assert row["adjusted_entity_filling"] == {"reason": "user_preferred_retry"}
    assert row["decision_drift_status"] == "stable"
    assert row["bias_correction_status"] == "reviewed"
    adjustment = row["slot_adjustments"][0]
    assert adjustment["adjustment_scope"] == "node"
    assert adjustment["target_node"] == "retry_failed_ticket"
    assert adjustment["slot_name"] == "reason"
    assert adjustment["adjusted_value"] == "user_preferred_retry"


def test_drift_reports_ok_workflow_missing_and_node_missing(tmp_path):
    user_memory = write_user_memory(tmp_path)
    projects, _ = write_project_fixture(tmp_path)
    turns = write_turns(tmp_path, count=1)
    build = run_projection(["build", "--user-memory", user_memory, "--projects", projects, "--turns", turns])
    assert build.returncode == 0, build.stderr

    drift = run_projection(["drift", "--user-memory", user_memory, "--projects", projects])
    assert drift.returncode == 0, drift.stderr
    rows = parse_jsonl((user_memory / "graph" / "task-rail-drift.jsonl").read_text(encoding="utf-8"))
    assert rows[0]["status"] == "ok"

    missing_node_mem = write_user_memory(tmp_path / "node-missing")
    projects_node, _ = write_project_fixture(tmp_path / "node-missing", include_node=False)
    turns_node = write_turns(tmp_path / "node-missing", count=1)
    assert run_projection(["build", "--user-memory", missing_node_mem, "--projects", projects_node, "--turns", turns_node]).returncode == 0
    drift_node = run_projection(["drift", "--user-memory", missing_node_mem, "--projects", projects_node])
    assert drift_node.returncode == 0, drift_node.stderr
    rows = parse_jsonl((missing_node_mem / "graph" / "task-rail-drift.jsonl").read_text(encoding="utf-8"))
    assert rows[0]["status"] == "node_missing"

    missing_workflow_mem = write_user_memory(tmp_path / "workflow-missing")
    projects_workflow, _ = write_project_fixture(tmp_path / "workflow-missing", include_workflow=False)
    turns_workflow = write_turns(tmp_path / "workflow-missing", count=1)
    assert run_projection(["build", "--user-memory", missing_workflow_mem, "--projects", projects_workflow, "--turns", turns_workflow]).returncode == 0
    drift_workflow = run_projection(["drift", "--user-memory", missing_workflow_mem, "--projects", projects_workflow])
    assert drift_workflow.returncode == 0, drift_workflow.stderr
    rows = parse_jsonl((missing_workflow_mem / "graph" / "task-rail-drift.jsonl").read_text(encoding="utf-8"))
    assert rows[0]["status"] == "workflow_missing"


def test_user_prompt_hook_does_not_run_task_rail_projection(tmp_path):
    session = tmp_path / "session.json"
    hook = ROOT / "skills" / "uug-grounding" / "hooks" / "ug-prompt-hook.py"
    proc = subprocess.run(
        [sys.executable, str(hook)],
        input=json.dumps({"prompt": "demo ticket retry"}),
        capture_output=True,
        text=True,
        timeout=15,
        env={"UG_SESSION": str(session)},
    )
    assert proc.returncode == 0
    assert not (tmp_path / "user-memory" / "graph" / "task-rail-preferences.jsonl").exists()

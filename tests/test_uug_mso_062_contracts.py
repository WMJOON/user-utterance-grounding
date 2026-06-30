import json
import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
GROUNDING = ROOT / "skills" / "uug-grounding"
USER_MEMORY = ROOT / "skills" / "uug-user-memory"


def run_cmd(args, **kwargs):
    return subprocess.run(
        [sys.executable, *map(str, args)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=15,
        **kwargs,
    )


def test_user_memory_schema_is_user_scope_only(tmp_path):
    data_dir = tmp_path / "user-memory"
    boot = run_cmd([USER_MEMORY / "scripts" / "bootstrap.py", data_dir])
    assert boot.returncode == 0, boot.stderr

    env = os.environ.copy()
    env["WORKMEM_DIR"] = str(data_dir)
    created = run_cmd(
        [
            USER_MEMORY / "scripts" / "wm_node.py",
            "new",
            "user-context",
            "--title",
            "MSO v0.6.3 user-scope contract",
            "--tags",
            "uug,mso-0.6.3",
        ],
        env=env,
    )
    assert created.returncode == 0, created.stderr

    validate = run_cmd([USER_MEMORY / "scripts" / "wm_node.py", "validate", data_dir], env=env)
    assert validate.returncode == 0, validate.stdout + validate.stderr

    schema = (data_dir / "schema.yaml").read_text(encoding="utf-8")
    assert "user-context" in schema
    assert "user-pattern" in schema
    assert "user-preference" in schema
    assert "worklog:" not in schema
    assert "auditlog:" not in schema
    assert "task_rail_preference" in schema
    assert (data_dir / "context" / "repositories").is_dir()
    assert (data_dir / "pattern" / "episodic").is_dir()
    assert (data_dir / "graph").is_dir()
    assert (data_dir / "references" / "json-schema" / "task-rail-preferences.schema.json").exists()
    assert (data_dir / "references" / "jsonl-queries" / "task-rail.jq").exists()


def test_user_prompt_hook_is_non_blocking_and_side_effect_free(tmp_path):
    session = tmp_path / "session.json"
    env = os.environ.copy()
    env["UG_SESSION"] = str(session)
    payload = json.dumps({"prompt": "의도 매칭이 없어도 hook은 막지 않는다"}, ensure_ascii=False)

    hook = subprocess.run(
        [sys.executable, str(GROUNDING / "hooks" / "ug-prompt-hook.py")],
        cwd=ROOT,
        input=payload,
        capture_output=True,
        text=True,
        timeout=15,
        env=env,
    )

    assert hook.returncode == 0
    assert not session.exists()


def test_uug_hook_can_be_disabled_for_other_repo_tests(tmp_path):
    env = os.environ.copy()
    env["UUG_HOOKS_DISABLED"] = "1"
    env["UG_SESSION"] = str(tmp_path / "session.json")
    hook = subprocess.run(
        [sys.executable, str(GROUNDING / "hooks" / "ug-prompt-hook.py")],
        cwd=ROOT,
        input=json.dumps({"prompt": "ticket-217 재실행"}),
        capture_output=True,
        text=True,
        timeout=15,
        env=env,
    )

    assert hook.returncode == 0
    assert hook.stdout == ""
    assert hook.stderr == ""


def test_uug_cli_ground_and_dispatch_can_be_disabled():
    env = os.environ.copy()
    env["UUG_DISABLED"] = "1"

    ground = run_cmd([GROUNDING / "scripts" / "ug.py", "ground", "ticket-217 재실행"], env=env)
    assert ground.returncode == 0
    assert "disabled" in ground.stdout

    dispatch = run_cmd(
        [GROUNDING / "scripts" / "ug.py", "dispatch", "--json", "ticket-217 재실행"],
        env=env,
    )
    assert dispatch.returncode == 0
    assert json.loads(dispatch.stdout)["status"] == "disabled"


def test_codex_installer_uses_config_toml_and_removes_legacy_hooks_json(tmp_path):
    home = tmp_path / "home"
    codex = home / ".codex"
    codex.mkdir(parents=True)
    legacy_cmd = 'python3 "$HOME/.codex/skills/uug-grounding/hooks/ug-prompt-hook.py"'
    (codex / "hooks.json").write_text(
        json.dumps(
            {
                "hooks": {
                    "UserPromptSubmit": [
                        {
                            "hooks": [
                                {"type": "command", "command": legacy_cmd},
                                {"type": "command", "command": "echo keep-me"},
                            ]
                        }
                    ]
                }
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    env = os.environ.copy()
    env["HOME"] = str(home)
    install = subprocess.run(
        ["bash", str(GROUNDING / "install.sh"), "--codex"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=15,
        env=env,
    )

    assert install.returncode == 0, install.stdout + install.stderr
    config = (codex / "config.toml").read_text(encoding="utf-8")
    assert "[features]" in config
    assert "hooks = true" in config
    assert "# BEGIN UUG_GROUNDING_HOOK" in config
    assert "[[hooks.UserPromptSubmit]]" in config
    assert legacy_cmd in config

    hooks_json = json.loads((codex / "hooks.json").read_text(encoding="utf-8"))
    remaining = hooks_json["hooks"]["UserPromptSubmit"][0]["hooks"]
    assert [h["command"] for h in remaining] == ["echo keep-me"]

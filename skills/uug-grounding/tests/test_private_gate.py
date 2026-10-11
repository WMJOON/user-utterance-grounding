"""Scan the whole release repository, including staged new/nested files."""
from pathlib import Path
import shutil
import subprocess

SOURCE = Path(__file__).resolve().parents[1] / "check-private.sh"

def run(*args, cwd):
    return subprocess.run(list(args), cwd=cwd, text=True, capture_output=True)

def setup(tmp_path):
    run("git", "init", "-q", cwd=tmp_path)
    script = tmp_path / "skills/uug-grounding/check-private.sh"
    script.parent.mkdir(parents=True)
    shutil.copy2(SOURCE, script)
    return script

def test_default_scan_includes_other_skill_and_hides_value(tmp_path):
    script = setup(tmp_path)
    file = tmp_path / "skills/other.py"
    private = "/" + "Users" + "/" + "sample" + "/private"
    file.write_text(private)
    run("git", "add", ".", cwd=tmp_path)
    result = run("bash", str(script), cwd=tmp_path)
    assert result.returncode == 1 and "other.py" in result.stdout
    assert private not in result.stdout

def test_nested_user_registry_is_blocked(tmp_path):
    script = setup(tmp_path)
    (script.parent / "projects.yaml").write_text("sample: {}")
    run("git", "add", ".", cwd=tmp_path)
    result = run("bash", str(script), cwd=tmp_path)
    assert result.returncode == 1 and "projects.yaml" in result.stdout

def test_secret_pattern_is_blocked_without_printing_secret(tmp_path):
    script = setup(tmp_path)
    secret = "ghp_" + "a" * 36
    (tmp_path / "credentials.txt").write_text(secret)
    run("git", "add", ".", cwd=tmp_path)
    result = run("bash", str(script), cwd=tmp_path)
    assert result.returncode == 1 and "credentials.txt" in result.stdout
    assert secret not in result.stdout

def test_clean_tracked_files_pass(tmp_path):
    script = setup(tmp_path)
    (tmp_path / "README.md").write_text("Portable UUG release")
    run("git", "add", ".", cwd=tmp_path)
    assert run("bash", str(script), cwd=tmp_path).returncode == 0

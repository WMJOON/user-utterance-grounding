"""ug.py ground 슬롯-필 결정 테스트 (subprocess). rc: 0=grounded, 2=HITL(reprompt/모호/미매칭).
세션 상태는 UG_SESSION 으로 격리(빈 임시 파일) → 결정적."""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

SKILL = Path(__file__).resolve().parent.parent
UG = SKILL / "scripts" / "ug.py"


def _ground(utt, session=None):
    """session: None=빈 세션(격리), dict=세션 상태 주입."""
    sess_path = tempfile.mktemp(suffix=".json")
    if session is not None:
        Path(sess_path).write_text(json.dumps(session), encoding="utf-8")
    env = {**os.environ, "UG_SESSION": sess_path}
    r = subprocess.run([sys.executable, str(UG), "ground", utt], capture_output=True, text=True, env=env)
    Path(sess_path).unlink(missing_ok=True)
    return r.returncode, r.stdout + r.stderr


def test_full_ground_resolves_target():
    rc, out = _ground("이 스킬 정리하자")
    assert rc == 0 and "tidy-organize" in out and "agent-toolkit-forge" in out


def test_required_slot_reprompts():
    rc, out = _ground("이 개념 KB에 추가해줘")          # concept(required, ask) 미충족
    assert rc == 2 and "add-to-knowledge" in out and "concept" in out


def test_research_not_shadowed_by_bare_kb():
    rc, out = _ground("리서치 돌려줘 KB 관련")           # 맨 'KB' trigger 제거 후 run-research 단독
    assert "run-research" in out and "모호" not in out


def test_zero_signal_reprompts_when_no_session():
    rc, out = _ground("착수하자")                        # 신호0 + 빈 세션 → target_project 미충족
    assert rc == 2 and "work-on-project" in out and "target_project" in out


def test_zero_signal_infers_from_last_project():
    rc, out = _ground("착수하자", session={"last_project": "agent-toolkit-forge"})
    assert rc == 0 and "work-on-project" in out and "agent-toolkit-forge" in out


def test_no_intent_match():
    rc, out = _ground("점심 뭐먹지")
    assert rc == 2 and "미매칭" in out

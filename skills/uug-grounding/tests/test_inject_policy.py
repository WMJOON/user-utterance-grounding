"""UD-0005 — 직전 작업 레포와 같은 대상이면 컨텍스트 주입 생략 정책."""
import sys
from pathlib import Path

import pytest

SKILL = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL / "scripts"))
sys.path.insert(0, str(SKILL / "hooks"))

import ug  # noqa: E402
from context_contract import format_context  # noqa: E402


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(ug, "INJECT_STATE", tmp_path / "inject-state.json")
    t = tmp_path / "transcript.jsonl"
    t.write_text('{"type":"user"}\n', encoding="utf-8")
    return t


def r(status, target, prev, **kw):
    return dict({"status": status, "emit": True, "prev": prev,
                 "candidates": [{"project": target, "path": f"/x/{target}"}]}, **kw)


def apply(res, t):
    return ug.apply_same_target_policy(res, str(t))


def test_first_injection_in_session_is_kept(env):
    assert apply(r("inferred", "a", "a"), env)["emit"] is True


def test_second_same_target_is_skipped(env):
    apply(r("inferred", "a", "a"), env)
    out = apply(r("clear", "a", "a"), env)
    assert out["emit"] is False and out["emit_reason"] == "same_as_prev"
    assert format_context(out) is None


def test_target_switch_is_kept(env):
    apply(r("inferred", "a", "a"), env)
    assert apply(r("clear", "b", "a"), env)["emit"] is True


def test_no_prev_is_kept(env):
    apply(r("clear", "a", None), env)
    assert apply(r("clear", "a", None), env)["emit"] is True


def test_clarify_continuity_skipped_after_contract(env):
    apply(r("inferred", "a", "a"), env)
    out = apply(r("clarify", "a", "a", recommended="a", recommended_by="연속성"), env)
    assert out["emit"] is False


def test_clarify_by_vocab_frequency_is_kept(env):
    """C3 가 직전 레포를 벗어나라고 추천하면 생략하지 않는다."""
    apply(r("inferred", "a", "a"), env)
    out = apply(r("clarify", "kb", "a", recommended="kb", recommended_by="작업어휘 빈도"), env)
    assert out["emit"] is True


def test_clarify_without_recommendation_is_kept(env):
    apply(r("inferred", "a", "a"), env)
    assert apply(r("clarify", "a", "a"), env)["emit"] is True


def test_clarify_does_not_count_as_contract(env):
    """clarify 는 대상 확인만 전달 — 그 뒤 같은 대상 첫 확정 주입은 유지."""
    apply(r("clarify", "a", "a", recommended="a", recommended_by="연속성"), env)
    assert apply(r("inferred", "a", "a"), env)["emit"] is True


@pytest.mark.parametrize("marker", [
    '{"type":"compacted","payload":{}}',                       # Codex (실기록 확인)
    '{"type":"system","subtype":"compact_boundary"}',          # Claude (알려진 형식)
    '{"type":"user","isCompactSummary":true}',
])
def test_reinject_after_compaction(env, marker):
    apply(r("inferred", "a", "a"), env)
    assert apply(r("inferred", "a", "a"), env)["emit"] is False
    with env.open("a", encoding="utf-8") as f:
        f.write(marker + "\n")
    assert apply(r("inferred", "a", "a"), env)["emit"] is True
    assert apply(r("inferred", "a", "a"), env)["emit"] is False


def test_state_is_per_transcript(env, tmp_path):
    apply(r("inferred", "a", "a"), env)
    other = tmp_path / "other.jsonl"
    other.write_text("{}\n", encoding="utf-8")
    assert apply(r("inferred", "a", "a"), other)["emit"] is True


def test_not_emitted_untouched(env):
    out = apply(dict(r("inferred", "a", "a"), emit=False, emit_reason="insufficient_agreement"), env)
    assert out["emit_reason"] == "insufficient_agreement"
    assert not ug.INJECT_STATE.exists()

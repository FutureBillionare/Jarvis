"""Tests for project_engine state machine."""
import sys, json, pytest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).parent.parent))

# ── Helpers ───────────────────────────────────────────────────────────────────

def _engine(tmp_path):
    """Return a ProjectEngine with a temp state file."""
    import project_engine as pe
    engine = pe.ProjectEngine.__new__(pe.ProjectEngine)
    engine._state_file = tmp_path / ".project_state.json"
    engine._state = pe._empty_state()
    engine._on_status = lambda s, label=None: None
    return engine


# ── State I/O ─────────────────────────────────────────────────────────────────

class TestStatePersistence:
    def test_empty_state_has_idle_phase(self, tmp_path):
        import project_engine as pe
        state = pe._empty_state()
        assert state["phase"] == "IDLE"
        assert state["questions"] == []
        assert state["design_sections"] == []

    def test_save_and_load_roundtrip(self, tmp_path):
        engine = _engine(tmp_path)
        engine._state["phase"] = "QUESTIONING"
        engine._state["project_name"] = "my-project"
        engine._save()
        engine2 = _engine(tmp_path)
        engine2._load()
        assert engine2._state["phase"] == "QUESTIONING"
        assert engine2._state["project_name"] == "my-project"

    def test_reset_clears_state(self, tmp_path):
        engine = _engine(tmp_path)
        engine._state["phase"] = "DESIGNING"
        engine._state["project_name"] = "old"
        engine.reset()
        assert engine._state["phase"] == "IDLE"
        assert engine._state["project_name"] == ""

    def test_load_missing_file_gives_idle_state(self, tmp_path):
        engine = _engine(tmp_path)
        engine._load()   # file does not exist
        assert engine._state["phase"] == "IDLE"


# ── Detection ─────────────────────────────────────────────────────────────────

class TestKeywordDetection:
    def test_build_triggers(self, tmp_path):
        import project_engine as pe
        assert pe._has_project_keywords("can you build me a payment system") is True

    def test_add_triggers(self, tmp_path):
        import project_engine as pe
        assert pe._has_project_keywords("add stripe integration") is True

    def test_greeting_does_not_trigger(self, tmp_path):
        import project_engine as pe
        assert pe._has_project_keywords("hey how are you") is False

    def test_question_does_not_trigger(self, tmp_path):
        import project_engine as pe
        assert pe._has_project_keywords("what time is it") is False

    def test_manual_trigger_detected(self, tmp_path):
        import project_engine as pe
        assert pe._is_manual_trigger("project mode: add stripe") is True
        assert pe._is_manual_trigger("/project add dark mode") is True
        assert pe._is_manual_trigger("build mode") is True
        assert pe._is_manual_trigger("just chatting") is False

    def test_cancel_detected(self, tmp_path):
        import project_engine as pe
        assert pe._is_cancel("cancel") is True
        assert pe._is_cancel("stop project mode") is True
        assert pe._is_cancel("exit project mode") is True
        assert pe._is_cancel("keep going") is False


# ── intercept() ───────────────────────────────────────────────────────────────

class TestIntercept:
    def test_cancel_resets_active_project(self, tmp_path):
        import project_engine as pe
        engine = _engine(tmp_path)
        engine._state["phase"] = "QUESTIONING"
        result = engine.intercept("cancel")
        assert result is not None
        assert engine.phase == "IDLE"

    def test_idle_non_project_returns_none(self, tmp_path):
        import project_engine as pe
        engine = _engine(tmp_path)
        with patch("project_engine._gemma_confirms_project", return_value=False):
            result = engine.intercept("what is the weather today")
        assert result is None
        assert engine.phase == "IDLE"

    def test_manual_trigger_enters_questioning(self, tmp_path):
        import project_engine as pe
        engine = _engine(tmp_path)
        with patch.object(engine, "_run_questioning", return_value="Question 1?") as mock_q:
            result = engine.intercept("project mode: add stripe payments")
        assert engine.phase == "QUESTIONING"
        mock_q.assert_called_once()

    def test_escalate_command_returns_escalation_message(self, tmp_path):
        import project_engine as pe
        engine = _engine(tmp_path)
        engine._state["phase"] = "DESIGNING"
        engine._state["project_name"] = "stripe"
        engine._state["spec_path"] = "/tmp/spec.md"
        result = engine.intercept("escalate")
        assert result is not None
        assert "stripe" in result.lower() or "spec" in result.lower() or "claude code" in result.lower()


# ── QUESTIONING phase ─────────────────────────────────────────────────────────

class TestQuestioning:
    def test_records_answer_and_asks_next(self, tmp_path):
        import project_engine as pe
        engine = _engine(tmp_path)
        engine._state["phase"] = "QUESTIONING"
        engine._state["description"] = "Add Stripe payments"

        with patch("project_engine._ask_question", return_value="▸ Q2 — What currency?"):
            result = engine._run_questioning("One-time payments only")

        assert len(engine._state["questions"]) == 1
        assert engine._state["questions"][0]["a"] == "One-time payments only"
        assert "Q2" in result

    def test_advances_to_designing_after_5_questions(self, tmp_path):
        import project_engine as pe
        engine = _engine(tmp_path)
        engine._state["phase"] = "QUESTIONING"
        engine._state["description"] = "Add Stripe"
        engine._state["questions"] = [
            {"q": f"Q{i}", "a": f"A{i}"} for i in range(4)
        ]
        with patch.object(engine, "_run_designing", return_value="▸ DESIGN — Architecture:"):
            with patch("project_engine._ask_question", return_value="▸ DESIGN — I have enough."):
                result = engine._run_questioning("Last answer")

        assert len(engine._state["questions"]) == 5

    def test_proceed_phrase_advances_to_designing(self, tmp_path):
        import project_engine as pe
        engine = _engine(tmp_path)
        engine._state["phase"] = "QUESTIONING"
        engine._state["questions"] = [{"q": "Q1", "a": "A1"}]
        with patch.object(engine, "_run_designing", return_value="▸ DESIGN —") as mock_d:
            engine._run_questioning("proceed")
        mock_d.assert_called_once()


# ── DESIGNING phase ───────────────────────────────────────────────────────────

class TestDesigning:
    def test_approval_phrase_marks_section_approved(self, tmp_path):
        import project_engine as pe
        engine = _engine(tmp_path)
        engine._state["phase"] = "DESIGNING"
        engine._state["design_sections"] = [
            {"name": "Architecture", "content": "...", "approved": False}
        ]
        with patch("project_engine._generate_design_section", return_value="▸ DESIGN — Components:"):
            result = engine._run_designing("yes looks good")
        assert engine._state["design_sections"][0]["approved"] is True

    def test_all_sections_approved_advances_to_planning(self, tmp_path):
        import project_engine as pe
        engine = _engine(tmp_path)
        engine._state["phase"] = "DESIGNING"
        engine._state["project_name"] = "test-project"
        engine._state["design_sections"] = [
            {"name": s, "content": "content", "approved": True}
            for s in ["Architecture", "Components & Data Flow", "Implementation Approach"]
        ]
        with patch.object(engine, "_write_spec", return_value="/tmp/spec.md"):
            with patch.object(engine, "_run_planning", return_value="▸ PLAN —") as mock_p:
                engine._run_designing("yes")
        mock_p.assert_called_once()
        assert engine.phase == "PLANNING"

from unittest.mock import AsyncMock, MagicMock

from src.agent.nodes import evaluate_quality, revise_review


def _make_llm_mock(function_name: str, args: dict):
    """Create a mock Gemini client that returns a function call response."""
    fc = MagicMock()
    fc.name = function_name
    fc.args = args

    part = MagicMock()
    part.function_call = fc

    candidate = MagicMock()
    candidate.content.parts = [part]

    response = MagicMock()
    response.candidates = [candidate]

    llm = MagicMock()
    llm.aio.models.generate_content = AsyncMock(return_value=response)
    return llm


def _make_llm_mock_no_function_call():
    """Create a mock Gemini client that returns no function call."""
    part = MagicMock()
    part.function_call = None

    candidate = MagicMock()
    candidate.content.parts = [part]

    response = MagicMock()
    response.candidates = [candidate]

    llm = MagicMock()
    llm.aio.models.generate_content = AsyncMock(return_value=response)
    return llm


class TestEvaluateQuality:
    async def test_returns_correct_keys(self):
        llm = _make_llm_mock(
            "submit_evaluation",
            {
                "score": 8,
                "feedback": "Good analysis",
                "is_high_risk": False,
            },
        )
        state = {
            "repo": "owner/repo",
            "pr_number": 1,
            "diff": "some diff",
            "issues": [],
            "suggestions": [],
            "summary": "Clean PR",
        }

        result = await evaluate_quality(state, llm=llm)

        assert result["score"] == 8
        assert result["revision_feedback"] == "Good analysis"
        assert result["is_high_risk"] is False

    async def test_high_risk_detection(self):
        llm = _make_llm_mock(
            "submit_evaluation",
            {
                "score": 7,
                "feedback": "Contains migration",
                "is_high_risk": True,
            },
        )
        state = {
            "repo": "owner/repo",
            "pr_number": 1,
            "diff": "ALTER TABLE users ADD COLUMN",
            "issues": [
                {"type": "security", "severity": "high", "file": "m.sql", "message": "migration"},
            ],
            "suggestions": [],
            "summary": "DB migration",
        }

        result = await evaluate_quality(state, llm=llm)

        assert result["is_high_risk"] is True
        assert result["score"] == 7

    async def test_fallback_when_no_function_call(self):
        llm = _make_llm_mock_no_function_call()
        state = {
            "repo": "owner/repo",
            "pr_number": 1,
            "diff": "diff",
            "issues": [],
            "suggestions": [],
            "summary": "",
        }

        result = await evaluate_quality(state, llm=llm)

        assert result["score"] == 5
        assert result["revision_feedback"] == "Evaluation failed"
        assert result["is_high_risk"] is False


class TestReviseReview:
    async def test_increments_retry_count(self):
        llm = _make_llm_mock(
            "submit_review",
            {
                "issues": [
                    {"type": "bug", "severity": "high", "file": "a.py", "message": "found it"}
                ],
                "suggestions": [],
                "summary": "Revised analysis",
            },
        )
        state = {
            "repo": "owner/repo",
            "pr_number": 1,
            "pr_title": "fix: something",
            "pr_description": "",
            "diff": "diff content",
            "changed_files": ["a.py"],
            "revision_feedback": "Missed a null check",
            "score": 4,
            "retry_count": 0,
        }

        result = await revise_review(state, llm=llm)

        assert result["retry_count"] == 1
        assert len(result["issues"]) == 1
        assert result["summary"] == "Revised analysis"

    async def test_second_retry(self):
        llm = _make_llm_mock(
            "submit_review",
            {
                "issues": [],
                "suggestions": [],
                "summary": "Better now",
            },
        )
        state = {
            "repo": "owner/repo",
            "pr_number": 1,
            "pr_title": "fix: thing",
            "pr_description": "",
            "diff": "diff",
            "changed_files": [],
            "revision_feedback": "Still missed something",
            "score": 3,
            "retry_count": 1,
        }

        result = await revise_review(state, llm=llm)

        assert result["retry_count"] == 2

    async def test_fallback_when_no_function_call(self):
        llm = _make_llm_mock_no_function_call()
        state = {
            "repo": "owner/repo",
            "pr_number": 1,
            "pr_title": "fix",
            "pr_description": "",
            "diff": "diff",
            "changed_files": [],
            "revision_feedback": "feedback",
            "score": 3,
            "retry_count": 0,
        }

        result = await revise_review(state, llm=llm)

        assert result["retry_count"] == 1
        assert result["issues"] == []
        assert "could not be completed" in result["summary"]

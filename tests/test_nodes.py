from src.agent.nodes import format_review


class TestFormatReview:
    def test_basic_format(self):
        state = {
            "repo": "owner/repo",
            "pr_number": 1,
            "issues": [
                {
                    "type": "bug",
                    "severity": "high",
                    "file": "src/main.py",
                    "message": "Null check missing",
                },
            ],
            "suggestions": [
                {"file": "src/utils.py", "suggestion": "Consider using a constant"},
            ],
            "summary": "Overall good PR with one critical issue.",
            "skipped_files": [],
        }
        result = format_review(state)
        body = result["review_body"]

        assert "AI Code Review" in body
        assert "REQUEST_CHANGES" in result["review_decision"]
        assert "Null check missing" in body
        assert "src/utils.py" in body
        assert "Overall good PR" in body

    def test_no_issues_approves(self):
        state = {
            "repo": "owner/repo",
            "pr_number": 1,
            "issues": [],
            "suggestions": [],
            "summary": "Clean code.",
            "skipped_files": [],
        }
        result = format_review(state)
        assert result["review_decision"] == "APPROVE"

    def test_medium_severity_comments(self):
        state = {
            "repo": "owner/repo",
            "pr_number": 1,
            "issues": [
                {"type": "style", "severity": "medium", "file": "a.py", "message": "Naming"},
            ],
            "suggestions": [],
            "summary": "",
            "skipped_files": [],
        }
        result = format_review(state)
        assert result["review_decision"] == "COMMENT"

    def test_skipped_files_notice(self):
        state = {
            "repo": "owner/repo",
            "pr_number": 1,
            "issues": [],
            "suggestions": [],
            "summary": "",
            "skipped_files": ["package-lock.json", "yarn.lock"],
        }
        result = format_review(state)
        assert "2 file(s) were skipped" in result["review_body"]

    def test_no_skipped_files_no_notice(self):
        state = {
            "repo": "owner/repo",
            "pr_number": 1,
            "issues": [],
            "suggestions": [],
            "summary": "",
            "skipped_files": [],
        }
        result = format_review(state)
        assert "skipped" not in result["review_body"]

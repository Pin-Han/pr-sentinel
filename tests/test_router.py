from src.agent.router import route_after_evaluate


class TestRouteAfterEvaluate:
    def test_low_score_first_retry(self):
        state = {"score": 3, "retry_count": 0, "is_high_risk": False}
        assert route_after_evaluate(state) == "revise_review"

    def test_low_score_second_retry(self):
        state = {"score": 4, "retry_count": 1, "is_high_risk": False}
        assert route_after_evaluate(state) == "revise_review"

    def test_low_score_retries_exhausted(self):
        state = {"score": 4, "retry_count": 2, "is_high_risk": False}
        assert route_after_evaluate(state) == "format_review"

    def test_high_risk_not_approved(self):
        state = {"score": 8, "retry_count": 0, "is_high_risk": True, "human_approved": None}
        assert route_after_evaluate(state) == "human_checkpoint"

    def test_high_risk_already_approved(self):
        state = {"score": 8, "retry_count": 0, "is_high_risk": True, "human_approved": True}
        assert route_after_evaluate(state) == "format_review"

    def test_normal_pass_through(self):
        state = {"score": 8, "retry_count": 0, "is_high_risk": False}
        assert route_after_evaluate(state) == "format_review"

    def test_low_score_takes_priority_over_high_risk(self):
        state = {"score": 3, "retry_count": 0, "is_high_risk": True}
        assert route_after_evaluate(state) == "revise_review"

    def test_high_risk_after_retries_exhausted(self):
        state = {"score": 3, "retry_count": 2, "is_high_risk": True, "human_approved": None}
        assert route_after_evaluate(state) == "human_checkpoint"

    def test_missing_fields_defaults_to_pass_through(self):
        assert route_after_evaluate({}) == "format_review"

from src.agent.state import PRReviewState


def route_after_evaluate(state: PRReviewState) -> str:
    """Route after evaluate_quality based on score and risk level.

    Priority: retry (low score) > HitL (high-risk) > pass-through.
    """
    if state.get("score", 10) < 6 and state.get("retry_count", 0) < 2:
        return "revise_review"
    if state.get("is_high_risk", False) and not state.get("human_approved"):
        return "human_checkpoint"
    return "format_review"

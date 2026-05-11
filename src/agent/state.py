from typing import TypedDict


class Issue(TypedDict):
    type: str  # "bug" | "security" | "performance" | "style"
    severity: str  # "high" | "medium" | "low"
    file: str
    message: str


class Suggestion(TypedDict):
    file: str
    suggestion: str


class PRReviewState(TypedDict, total=False):
    # -- Input (from webhook payload) --
    repo: str  # "owner/repo"
    pr_number: int
    pr_title: str
    pr_description: str

    # -- Diff data (populated by fetch_diff) --
    diff: str
    changed_files: list[str]
    skipped_files: list[str]

    # -- Analysis (populated by analyze_code) --
    issues: list[Issue]
    suggestions: list[Suggestion]
    summary: str

    # -- Evaluation (Phase 2) --
    score: int  # 0-10
    revision_feedback: str
    retry_count: int  # default 0, max 2

    # -- Flow control (Phase 3) --
    is_high_risk: bool
    human_approved: bool | None

    # -- Output --
    review_body: str
    review_decision: str  # "APPROVE" | "REQUEST_CHANGES" | "COMMENT"

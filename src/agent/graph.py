import functools

from google import genai
from langgraph.graph import END, StateGraph

from src.agent.nodes import (
    analyze_code,
    evaluate_quality,
    fetch_diff,
    format_review,
    human_checkpoint,
    post_review,
    revise_review,
)
from src.agent.router import route_after_evaluate
from src.agent.state import PRReviewState
from src.github.client import GitHubClient


def build_graph(github: GitHubClient, llm: genai.Client, checkpointer=None) -> StateGraph:
    """Build the PR review graph with evaluate/retry cycle and HitL checkpoint.

    fetch_diff → analyze_code → evaluate_quality
      ├─→ revise_review → evaluate_quality (cycle, max 2)
      ├─→ human_checkpoint → format_review → post_review
      └─→ format_review → post_review → END
    """
    graph = StateGraph(PRReviewState)

    # Bind dependencies via functools.partial
    graph.add_node("fetch_diff", functools.partial(fetch_diff, github=github))
    graph.add_node("analyze_code", functools.partial(analyze_code, llm=llm))
    graph.add_node("evaluate_quality", functools.partial(evaluate_quality, llm=llm))
    graph.add_node("revise_review", functools.partial(revise_review, llm=llm))
    graph.add_node("human_checkpoint", human_checkpoint)
    graph.add_node("format_review", format_review)
    graph.add_node("post_review", functools.partial(post_review, github=github))

    # Linear head
    graph.set_entry_point("fetch_diff")
    graph.add_edge("fetch_diff", "analyze_code")
    graph.add_edge("analyze_code", "evaluate_quality")

    # Conditional branching after evaluation
    graph.add_conditional_edges(
        "evaluate_quality",
        route_after_evaluate,
        {
            "revise_review": "revise_review",
            "human_checkpoint": "human_checkpoint",
            "format_review": "format_review",
        },
    )

    # Cycle: revise feeds back into evaluate
    graph.add_edge("revise_review", "evaluate_quality")

    # After human approval, proceed to format
    graph.add_edge("human_checkpoint", "format_review")

    # Linear tail
    graph.add_edge("format_review", "post_review")
    graph.add_edge("post_review", END)

    return graph.compile(checkpointer=checkpointer)

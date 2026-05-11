import functools

import anthropic
from langgraph.graph import END, StateGraph

from src.agent.nodes import analyze_code, fetch_diff, format_review, post_review
from src.agent.state import PRReviewState
from src.github.client import GitHubClient


def build_graph(github: GitHubClient, llm: anthropic.AsyncAnthropic) -> StateGraph:
    """Build the Phase 1 PR review graph (linear flow).

    fetch_diff → analyze_code → format_review → post_review
    """
    graph = StateGraph(PRReviewState)

    # Bind dependencies via functools.partial
    graph.add_node("fetch_diff", functools.partial(fetch_diff, github=github))
    graph.add_node("analyze_code", functools.partial(analyze_code, llm=llm))
    graph.add_node("format_review", format_review)
    graph.add_node("post_review", functools.partial(post_review, github=github))

    graph.set_entry_point("fetch_diff")
    graph.add_edge("fetch_diff", "analyze_code")
    graph.add_edge("analyze_code", "format_review")
    graph.add_edge("format_review", "post_review")
    graph.add_edge("post_review", END)

    return graph.compile()

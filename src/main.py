import asyncio
import logging
import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from google import genai
from langgraph.types import Command
from pydantic import BaseModel

from src.agent.graph import build_graph
from src.checkpointer import create_checkpointer
from src.github.client import GitHubClient
from src.github.webhook import PREvent, parse_webhook

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# Global state
_github: GitHubClient | None = None
_llm: genai.Client | None = None
_graph = None

# In-flight review tracking for deduplication
# Key: (repo, pr_number) → Value: (head_sha, asyncio.Task)
_inflight: dict[tuple[str, int], tuple[str, asyncio.Task]] = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _github, _llm, _graph

    _github = GitHubClient(os.environ["GITHUB_TOKEN"])
    _llm = genai.Client(api_key=os.environ["GOOGLE_API_KEY"])

    async with create_checkpointer() as checkpointer:
        _graph = build_graph(_github, _llm, checkpointer=checkpointer)
        logger.info("PR Sentinel started")
        yield

    await _github.close()
    # Cancel all in-flight tasks
    for _, (_, task) in _inflight.items():
        task.cancel()
    logger.info("PR Sentinel stopped")


app = FastAPI(title="PR Sentinel", version="0.2.0", lifespan=lifespan)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "version": "0.2.0"}


@app.post("/webhook/github")
async def webhook_handler(request: Request) -> dict:
    webhook_secret = os.environ["GITHUB_WEBHOOK_SECRET"]
    event_type = request.headers.get("X-GitHub-Event", "unknown")
    logger.info("Webhook received: event_type=%s", event_type)

    event = await parse_webhook(request, webhook_secret)

    if event is None:
        logger.info("Webhook ignored (not a relevant PR event)")
        return {"status": "ignored"}

    logger.info(
        "Webhook accepted: %s #%d (%s) @ %s",
        event.repo_full_name,
        event.pr_number,
        event.action,
        event.head_sha,
    )
    _schedule_review(event)
    return {"status": "accepted"}


def _schedule_review(event: PREvent) -> None:
    """Schedule a review, cancelling any in-flight review for the same PR."""
    key = (event.repo_full_name, event.pr_number)

    # Deduplication: cancel existing task for same PR if head_sha differs
    if key in _inflight:
        old_sha, old_task = _inflight[key]
        if old_sha == event.head_sha:
            logger.info("Skipping duplicate event for %s #%d @ %s", *key, event.head_sha)
            return
        old_task.cancel()
        logger.info(
            "Cancelled stale review for %s #%d (old: %s, new: %s)", *key, old_sha, event.head_sha
        )

    task = asyncio.create_task(_run_review(event))
    _inflight[key] = (event.head_sha, task)


async def _run_review(event: PREvent) -> None:
    """Execute the review graph for a PR event."""
    key = (event.repo_full_name, event.pr_number)
    try:
        logger.info(
            "Starting review for %s #%d @ %s",
            event.repo_full_name,
            event.pr_number,
            event.head_sha,
        )

        # Post acknowledgement comment immediately
        await _github.post_comment(
            event.repo_full_name,
            event.pr_number,
            "🔍 **PR Sentinel** is reviewing this pull request… Results will be posted shortly.",
        )

        initial_state = {
            "repo": event.repo_full_name,
            "pr_number": event.pr_number,
            "pr_title": event.pr_title,
            "pr_description": event.pr_description,
            "retry_count": 0,
            "is_high_risk": False,
            "human_approved": None,
        }

        config = {
            "configurable": {
                "thread_id": f"{event.repo_full_name}:{event.pr_number}:{event.head_sha}",
            }
        }

        await _graph.ainvoke(initial_state, config=config)
        logger.info("Completed review for %s #%d", event.repo_full_name, event.pr_number)

    except asyncio.CancelledError:
        logger.info("Review cancelled for %s #%d", event.repo_full_name, event.pr_number)
    except Exception:
        logger.exception("Review failed for %s #%d", event.repo_full_name, event.pr_number)
    finally:
        _inflight.pop(key, None)


# ---------------------------------------------------------------------------
# HitL resume & status endpoints
# ---------------------------------------------------------------------------


class ResumeRequest(BaseModel):
    repo: str
    pr_number: int
    head_sha: str
    approved: bool


@app.post("/review/resume")
async def resume_review(req: ResumeRequest) -> dict:
    """Resume an interrupted high-risk review with human decision."""
    thread_id = f"{req.repo}:{req.pr_number}:{req.head_sha}"
    config = {"configurable": {"thread_id": thread_id}}

    state = await _graph.aget_state(config)
    if (
        not state
        or not state.tasks
        or not any(hasattr(t, "interrupts") and t.interrupts for t in state.tasks)
    ):
        return {"status": "error", "message": "No interrupted review found for this thread"}

    await _graph.ainvoke(Command(resume={"approved": req.approved}), config=config)
    return {"status": "resumed", "approved": req.approved}


@app.get("/review/status/{repo:path}/{pr_number}/{head_sha}")
async def review_status(repo: str, pr_number: int, head_sha: str) -> dict:
    """Check whether a review is interrupted (awaiting human approval)."""
    thread_id = f"{repo}:{pr_number}:{head_sha}"
    config = {"configurable": {"thread_id": thread_id}}

    state = await _graph.aget_state(config)
    if not state or not state.values:
        return {"status": "not_found"}

    interrupted = any(hasattr(t, "interrupts") and t.interrupts for t in (state.tasks or []))
    if interrupted:
        interrupt_data = state.tasks[0].interrupts[0].value
        return {"status": "interrupted", "interrupt_data": interrupt_data}

    return {"status": "completed"}

import asyncio
import logging
import os

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from google import genai

from src.agent.graph import build_graph
from src.github.client import GitHubClient
from src.github.webhook import PREvent, parse_webhook

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(title="PR Sentinel", version="0.1.0")

# Global state
_github: GitHubClient | None = None
_llm: genai.Client | None = None
_graph = None

# In-flight review tracking for deduplication
# Key: (repo, pr_number) → Value: (head_sha, asyncio.Task)
_inflight: dict[tuple[str, int], tuple[str, asyncio.Task]] = {}


@app.on_event("startup")
async def startup() -> None:
    global _github, _llm, _graph

    github_token = os.environ["GITHUB_TOKEN"]
    _github = GitHubClient(github_token)
    _llm = genai.Client(api_key=os.environ["GOOGLE_API_KEY"])
    _graph = build_graph(_github, _llm)
    logger.info("PR Sentinel started")


@app.on_event("shutdown")
async def shutdown() -> None:
    if _github:
        await _github.close()
    # Cancel all in-flight tasks
    for _, (_, task) in _inflight.items():
        task.cancel()
    logger.info("PR Sentinel stopped")


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "version": "0.1.0"}


@app.post("/webhook/github")
async def webhook_handler(request: Request) -> dict:
    webhook_secret = os.environ["GITHUB_WEBHOOK_SECRET"]
    event = await parse_webhook(request, webhook_secret)

    if event is None:
        return {"status": "ignored"}

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
        logger.info("Cancelled stale review for %s #%d (old: %s, new: %s)",
                     *key, old_sha, event.head_sha)

    task = asyncio.create_task(_run_review(event))
    _inflight[key] = (event.head_sha, task)


async def _run_review(event: PREvent) -> None:
    """Execute the review graph for a PR event."""
    key = (event.repo_full_name, event.pr_number)
    try:
        logger.info("Starting review for %s #%d @ %s", event.repo_full_name,
                     event.pr_number, event.head_sha)

        initial_state = {
            "repo": event.repo_full_name,
            "pr_number": event.pr_number,
            "pr_title": event.pr_title,
            "pr_description": event.pr_description,
            "retry_count": 0,
            "is_high_risk": False,
            "human_approved": None,
        }

        await _graph.ainvoke(initial_state)
        logger.info("Completed review for %s #%d", event.repo_full_name, event.pr_number)

    except asyncio.CancelledError:
        logger.info("Review cancelled for %s #%d", event.repo_full_name, event.pr_number)
    except Exception:
        logger.exception("Review failed for %s #%d", event.repo_full_name, event.pr_number)
    finally:
        _inflight.pop(key, None)

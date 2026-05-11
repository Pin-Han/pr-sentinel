# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Install dependencies
pip install -e ".[dev]"

# Run all tests
pytest

# Run a single test file or test
pytest tests/test_diff.py
pytest tests/test_nodes.py::TestFormatReview::test_basic_format

# Lint
ruff check src/ tests/
ruff format --check src/ tests/

# Run dev server locally
uvicorn src.main:app --reload --port 8000
```

## Architecture

PR Sentinel is a LangGraph-based agent that automatically reviews GitHub PRs via webhooks.

**Request flow**: GitHub webhook → FastAPI (`src/main.py`) → signature verification → immediate 200 response → background `asyncio.create_task` → LangGraph graph execution → post review back to GitHub.

**Deduplication**: `src/main.py` tracks in-flight reviews by `(repo, pr_number)` → `(head_sha, task)`. Rapid pushes cancel stale tasks and start fresh reviews for the new HEAD.

**LangGraph graph** (`src/agent/graph.py`): Nodes receive external dependencies (GitHub client, Gemini client) via `functools.partial`. Each node returns only the state keys it updates, not the full state.

Current graph (Phase 1, linear):
```
fetch_diff → analyze_code → format_review → post_review
```

Planned (Phase 2+): evaluate_quality node with conditional edges creating a retry cycle (score < 6 → revise → re-evaluate, max 2 retries), plus HitL checkpoint via `interrupt()` for high-risk changes.

**LLM integration**: `analyze_code` calls the Google Gemini API directly via `google-genai` SDK (not via LangChain wrapper) using function calling with forced mode (`ANY`) to guarantee structured JSON output. The tool schema is defined in `src/agent/prompts.py` using `google.genai.types`.

**Diff processing** (`src/github/diff.py`): Files are included whole or skipped entirely (never cut mid-hunk). Lockfiles, generated files, and binary assets are auto-skipped. Token budget is ~50K tokens (200K chars).

**GitHub API** (`src/github/client.py`): Uses `httpx.AsyncClient` directly (not PyGithub) to stay fully async with FastAPI.

## Deployment

Deployed to Railway with a persistent volume at `/data` for SQLite checkpoint storage. The `railway.toml` configures the volume mount and health check endpoint.

Required env vars: `GOOGLE_API_KEY`, `GITHUB_TOKEN`, `GITHUB_WEBHOOK_SECRET`. See `.env.example`.

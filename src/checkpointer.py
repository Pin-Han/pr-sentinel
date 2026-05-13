import os
from pathlib import Path

from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver


def _default_db_path() -> str:
    """Return the checkpoint DB path, falling back to local .data/ for development."""
    path = os.getenv("CHECKPOINT_DB_PATH", "/data/checkpoints.db")
    parent = Path(path).parent
    if parent.exists() and os.access(parent, os.W_OK):
        return path
    # Fallback for local development where /data is not available
    local = Path(__file__).resolve().parent.parent / ".data" / "checkpoints.db"
    local.parent.mkdir(parents=True, exist_ok=True)
    return str(local)


def create_checkpointer(db_path: str | None = None) -> AsyncSqliteSaver:
    """Create an async SQLite checkpointer for LangGraph HitL support."""
    if db_path is None:
        db_path = _default_db_path()
    return AsyncSqliteSaver.from_conn_string(db_path)

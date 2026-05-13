import logging
import os
import sqlite3
from pathlib import Path

from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

logger = logging.getLogger(__name__)

_CANDIDATES = [
    "/data/checkpoints.db",       # Railway persistent volume
    "/tmp/checkpoints.db",        # Ephemeral fallback on Railway/containers
]


def _default_db_path() -> str:
    """Pick the first writable checkpoint DB path by actually trying to open SQLite."""
    override = os.getenv("CHECKPOINT_DB_PATH")
    if override:
        Path(override).parent.mkdir(parents=True, exist_ok=True)
        return override

    for candidate in _CANDIDATES:
        parent = Path(candidate).parent
        try:
            parent.mkdir(parents=True, exist_ok=True)
            # Actually try opening SQLite — the only reliable writability check
            conn = sqlite3.connect(candidate)
            conn.close()
            logger.info("Using checkpoint DB at %s", candidate)
            return candidate
        except (OSError, sqlite3.OperationalError):
            continue

    # Last resort: project-local .data/
    local = Path(__file__).resolve().parent.parent / ".data" / "checkpoints.db"
    local.parent.mkdir(parents=True, exist_ok=True)
    logger.info("Using checkpoint DB at %s", local)
    return str(local)


def create_checkpointer(db_path: str | None = None) -> AsyncSqliteSaver:
    """Create an async SQLite checkpointer for LangGraph HitL support."""
    if db_path is None:
        db_path = _default_db_path()
    return AsyncSqliteSaver.from_conn_string(db_path)

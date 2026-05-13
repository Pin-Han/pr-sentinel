from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver


def create_checkpointer(db_path: str = "/data/checkpoints.db") -> AsyncSqliteSaver:
    """Create an async SQLite checkpointer for LangGraph HitL support."""
    return AsyncSqliteSaver.from_conn_string(db_path)

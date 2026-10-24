"""SQLite database connection and session management with WAL mode."""

from contextlib import contextmanager
from pathlib import Path
import sqlite3
import threading
from typing import Generator, Optional, Union

from evodev.config import EvoDevConfig, load_config


class DatabaseManager:
    """Manages SQLite connections, pragmas, transactions, and lifecycle."""

    def __init__(self, db_path: Union[str, Path] = ":memory:"):
        self.db_path = str(db_path)
        self._local = threading.local()
        self._all_conns = []
        self._lock = threading.Lock()
        self._is_memory = self.db_path == ":memory:"

    def get_connection(self) -> sqlite3.Connection:
        """Get or create a thread-local SQLite connection configured with robust pragmas."""
        if not hasattr(self._local, "conn") or self._local.conn is None:
            if not self._is_memory:
                Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)

            conn = sqlite3.connect(
                self.db_path,
                timeout=30.0,
                check_same_thread=False,
            )
            conn.row_factory = sqlite3.Row

            # Apply robust SQLite pragmas
            if not self._is_memory:
                conn.execute("PRAGMA journal_mode = WAL;")
                conn.execute("PRAGMA synchronous = NORMAL;")
            conn.execute("PRAGMA foreign_keys = ON;")
            conn.execute("PRAGMA busy_timeout = 10000;")

            self._local.conn = conn
            with self._lock:
                self._all_conns.append(conn)

        return self._local.conn

    @contextmanager
    def session(self) -> Generator[sqlite3.Connection, None, None]:
        """Context manager providing an active transactional connection with auto-commit."""
        conn = self.get_connection()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise

    def close(self) -> None:
        """Close all connections across all threads."""
        with self._lock:
            for c in self._all_conns:
                try:
                    c.close()
                except Exception:
                    pass
            self._all_conns.clear()
        if hasattr(self._local, "conn"):
            self._local.conn = None


_DB_MANAGER: Optional[DatabaseManager] = None


def get_db(config: Optional[EvoDevConfig] = None) -> DatabaseManager:
    """Get the singleton DatabaseManager instance based on configuration."""
    global _DB_MANAGER
    if config is not None:
        target_path = str(config.db_path)
        if _DB_MANAGER is not None and _DB_MANAGER.db_path != target_path:
            _DB_MANAGER.close()
            _DB_MANAGER = None
    if _DB_MANAGER is None:
        cfg = config or load_config()
        _DB_MANAGER = DatabaseManager(cfg.db_path)
    return _DB_MANAGER


def set_db(db_manager: DatabaseManager) -> None:
    """Set the database manager instance (useful for unit testing with in-memory DB)."""
    global _DB_MANAGER
    _DB_MANAGER = db_manager


def close_db() -> None:
    """Close and reset singleton database manager."""
    global _DB_MANAGER
    if _DB_MANAGER is not None:
        _DB_MANAGER.close()
        _DB_MANAGER = None

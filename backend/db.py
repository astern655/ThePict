import os
import sqlite3
from contextlib import closing


def _db_path() -> str:
    return os.environ.get(
        "HOHOWATT_DB", os.path.join(os.path.dirname(__file__), "hohowatt.db")
    )


SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    email TEXT PRIMARY KEY,
    password_hash TEXT NOT NULL,
    gender TEXT,
    age INTEGER,
    height_cm REAL,
    weight_kg REAL,
    goal TEXT
);
CREATE TABLE IF NOT EXISTS tokens (
    token TEXT PRIMARY KEY,
    email TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    email TEXT NOT NULL,
    exercise_id TEXT NOT NULL,
    date TEXT NOT NULL,
    started_at TEXT NOT NULL,
    sets_json TEXT NOT NULL,
    total_reps INTEGER NOT NULL,
    avg_form_score REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS program_overrides (
    email TEXT NOT NULL,
    exercise_id TEXT NOT NULL,
    level TEXT,
    sets INTEGER,
    reps INTEGER,
    rest_sec INTEGER,
    PRIMARY KEY (email, exercise_id)
);
"""


def init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)


def init_once() -> None:
    """프로세스당 한 번만 스키마를 만든다.

    요청마다 executescript(DDL)를 돌릴 이유가 없어 옮긴 것뿐이다.
    (동시 요청 실패의 원인은 이게 아니라 get_db의 check_same_thread였다.)
    """
    with closing(sqlite3.connect(_db_path())) as conn:
        init_schema(conn)
        conn.commit()


def get_db():
    """Per-request connection (D3). Caller commits after writes.

    check_same_thread=False가 필요한 이유:
    FastAPI는 제너레이터 의존성의 셋업·엔드포인트·티어다운을 각각 다른
    스레드풀 워커에서 실행할 수 있다. 동시 요청이 들어오면 스레드가 섞여
    "SQLite objects created in a thread can only be used in that same thread"로
    500이 난다(순차 요청일 땐 같은 스레드가 재사용돼 드러나지 않는다).
    커넥션은 요청당 하나이고 두 스레드가 동시에 만지지는 않으므로 안전하다.
    """
    conn = sqlite3.connect(_db_path(), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def row_to_dict(row: "sqlite3.Row | None") -> dict | None:
    return dict(row) if row is not None else None


init_once()


def reset() -> None:
    """Wipe all tables. Used by tests instead of clearing in-memory dicts."""
    with closing(sqlite3.connect(_db_path())) as conn:
        conn.executescript(
            """
            DROP TABLE IF EXISTS users;
            DROP TABLE IF EXISTS tokens;
            DROP TABLE IF EXISTS sessions;
            DROP TABLE IF EXISTS program_overrides;
            """
        )
        init_schema(conn)
        conn.commit()

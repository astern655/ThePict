import hashlib
import imghdr
import json
import os
import sqlite3
import uuid
from datetime import date as date_cls
from typing import Literal, Optional

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

import analysis
import db
import pose_estimator
import pose_eval
import program

app = FastAPI()
# ponytail: 로컬 테스트용 전체 허용 — 배포 시 origin 목록으로 제한
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

EXERCISES = [
    {
        "id": "squat",
        "name": "스쿼트",
        "target": "하체 전반 (대퇴사두근, 둔근, 햄스트링)",
        "difficulty": "beginner",
        "steps": [
            "발을 어깨너비로 벌리고 발끝을 살짝 바깥으로 향한다",
            "가슴을 펴고 시선은 정면을 유지한다",
            "엉덩이를 뒤로 빼며 무릎을 굽혀 앉는다",
            "허벅지가 바닥과 평행할 때까지 내려간다",
            "발뒤꿈치로 바닥을 밀어내며 일어선다",
        ],
        "cautions": [
            "무릎이 발끝보다 안쪽으로 모이지 않게 한다",
            "허리가 둥글게 말리지 않도록 코어에 힘을 준다",
            "무릎이 발끝을 과도하게 넘어가지 않게 한다",
        ],
        "supported": True,
    },
    {
        "id": "deadlift",
        "name": "데드리프트",
        "target": "후면 사슬 (햄스트링, 둔근, 척추기립근)",
        "difficulty": "intermediate",
        "steps": [],
        "cautions": [],
        "supported": False,
    },
    {
        "id": "bench_press",
        "name": "벤치프레스",
        "target": "가슴, 어깨, 삼두",
        "difficulty": "intermediate",
        "steps": [],
        "cautions": [],
        "supported": False,
    },
    {
        "id": "lunge",
        "name": "런지",
        "target": "하체 (대퇴사두근, 둔근)",
        "difficulty": "beginner",
        "steps": [],
        "cautions": [],
        "supported": False,
    },
    {
        "id": "pushup",
        "name": "푸시업",
        "target": "가슴, 어깨, 삼두",
        "difficulty": "beginner",
        "steps": [],
        "cautions": [],
        "supported": False,
    },
]
for e in EXERCISES:
    if not e["supported"]:
        e["steps"] = ["준비 중"]
        e["cautions"] = ["준비 중"]
    e["presets"] = program.presets_for(e["id"])


# ---- password hashing (D2): pbkdf2_hmac, single-string storage ----
PBKDF2_ITERATIONS = 260_000


def hash_pw(password: str, salt: Optional[bytes] = None) -> str:
    if salt is None:
        salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, PBKDF2_ITERATIONS)
    return f"pbkdf2_sha256${PBKDF2_ITERATIONS}${salt.hex()}${dk.hex()}"


def verify_pw(password: str, stored: str) -> bool:
    try:
        scheme, iterations, salt_hex, hash_hex = stored.split("$")
    except ValueError:
        return False
    if scheme != "pbkdf2_sha256":
        return False
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt_hex), int(iterations))
    return dk.hex() == hash_hex


class AuthBody(BaseModel):
    email: str
    password: str


class ProfileUpdate(BaseModel):
    gender: Optional[str] = None
    age: Optional[int] = None
    height_cm: Optional[float] = None
    weight_kg: Optional[float] = None
    goal: Optional[str] = None


class CheckIn(BaseModel):
    """pose_eval.evaluate()가 낸 관절 판정 하나. 세트 종료 시 프런트가 그대로 올린다."""

    name: str
    value: float
    status: Literal["ok", "bad"]
    message: str = ""


class SetIn(BaseModel):
    reps: int
    form_score: float
    # 없으면 없는 대로 저장된다 — 기존 세션/카메라 없이 한 세션과 동일하게 동작
    checks: Optional[list[CheckIn]] = None


class SessionIn(BaseModel):
    exercise_id: str
    started_at: str
    sets: list[SetIn]


class ProgramOverride(BaseModel):
    """PUT은 행 전체를 대체한다. 빠진 필드는 null로 저장돼 프리셋/점진증가로 되돌아간다."""

    level: Optional[Literal["beginner", "intermediate", "advanced"]] = None
    sets: Optional[int] = Field(None, ge=1, le=10)
    reps: Optional[int] = Field(None, ge=1, le=100)
    rest_sec: Optional[int] = Field(None, ge=0, le=600)


def _user_out(user_row: dict) -> dict:
    return {k: v for k, v in user_row.items() if k != "password_hash"}


def get_current_user(
    authorization: Optional[str] = Header(None),
    conn: sqlite3.Connection = Depends(db.get_db),
) -> dict:
    if authorization is None or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="invalid auth header")
    token = authorization.removeprefix("Bearer ")
    row = conn.execute("SELECT email FROM tokens WHERE token = ?", (token,)).fetchone()
    if row is None:
        raise HTTPException(status_code=401, detail="invalid token")
    user_row = conn.execute("SELECT * FROM users WHERE email = ?", (row["email"],)).fetchone()
    if user_row is None:
        raise HTTPException(status_code=401, detail="invalid token")
    return db.row_to_dict(user_row)


@app.post("/auth/register", status_code=201)
def register(body: AuthBody, conn: sqlite3.Connection = Depends(db.get_db)):
    existing = conn.execute("SELECT 1 FROM users WHERE email = ?", (body.email,)).fetchone()
    if existing is not None:
        raise HTTPException(status_code=409, detail="email already registered")
    conn.execute(
        "INSERT INTO users (email, password_hash, gender, age, height_cm, weight_kg, goal) "
        "VALUES (?, ?, NULL, NULL, NULL, NULL, NULL)",
        (body.email, hash_pw(body.password)),
    )
    token = str(uuid.uuid4())
    conn.execute("INSERT INTO tokens (token, email) VALUES (?, ?)", (token, body.email))
    conn.commit()
    return {"token": token}


@app.post("/auth/login")
def login(body: AuthBody, conn: sqlite3.Connection = Depends(db.get_db)):
    user_row = conn.execute("SELECT * FROM users WHERE email = ?", (body.email,)).fetchone()
    if user_row is None or not verify_pw(body.password, user_row["password_hash"]):
        raise HTTPException(status_code=401, detail="invalid credentials")
    token = str(uuid.uuid4())
    conn.execute("INSERT INTO tokens (token, email) VALUES (?, ?)", (token, body.email))
    conn.commit()
    return {"token": token}


@app.get("/me/profile")
def get_profile(user: dict = Depends(get_current_user)):
    return _user_out(user)


@app.put("/me/profile")
def update_profile(
    body: ProfileUpdate,
    user: dict = Depends(get_current_user),
    conn: sqlite3.Connection = Depends(db.get_db),
):
    updates = body.model_dump(exclude_unset=True)
    if updates:
        set_clause = ", ".join(f"{field} = ?" for field in updates)
        conn.execute(
            f"UPDATE users SET {set_clause} WHERE email = ?",
            (*updates.values(), user["email"]),
        )
        conn.commit()
        user = {**user, **updates}
    return _user_out(user)


@app.delete("/me", status_code=204)
def delete_me(user: dict = Depends(get_current_user), conn: sqlite3.Connection = Depends(db.get_db)):
    email = user["email"]
    conn.execute("DELETE FROM sessions WHERE email = ?", (email,))
    conn.execute("DELETE FROM program_overrides WHERE email = ?", (email,))
    conn.execute("DELETE FROM tokens WHERE email = ?", (email,))
    conn.execute("DELETE FROM users WHERE email = ?", (email,))
    conn.commit()
    return None


@app.get("/exercises")
def list_exercises():
    return [{k: v for k, v in e.items()} for e in EXERCISES]


def _row_session(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"],
        "exercise_id": row["exercise_id"],
        "date": row["date"],
        "started_at": row["started_at"],
        "sets": json.loads(row["sets_json"]),
        "total_reps": row["total_reps"],
        "avg_form_score": row["avg_form_score"],
    }


@app.post("/sessions", status_code=201)
def create_session(
    body: SessionIn,
    user: dict = Depends(get_current_user),
    conn: sqlite3.Connection = Depends(db.get_db),
):
    sets = [s.model_dump(exclude_none=True) for s in body.sets]
    total_reps = sum(s["reps"] for s in sets)
    avg_form_score = sum(s["form_score"] for s in sets) / len(sets) if sets else 0
    sid = str(uuid.uuid4())
    conn.execute(
        "INSERT INTO sessions (id, email, exercise_id, date, started_at, sets_json, total_reps, avg_form_score) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (
            sid,
            user["email"],
            body.exercise_id,
            body.started_at[:10],
            body.started_at,
            json.dumps(sets),
            total_reps,
            avg_form_score,
        ),
    )
    conn.commit()
    return {
        "id": sid,
        "exercise_id": body.exercise_id,
        "date": body.started_at[:10],
        "started_at": body.started_at,
        "sets": sets,
        "total_reps": total_reps,
        "avg_form_score": avg_form_score,
    }


@app.get("/sessions")
def get_sessions(
    date: Optional[str] = None,
    user: dict = Depends(get_current_user),
    conn: sqlite3.Connection = Depends(db.get_db),
):
    if date is None:
        rows = conn.execute(
            "SELECT * FROM sessions WHERE email = ? ORDER BY started_at", (user["email"],)
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM sessions WHERE email = ? AND date = ? ORDER BY started_at",
            (user["email"], date),
        ).fetchall()
    return [_row_session(r) for r in rows]


@app.get("/calendar")
def get_calendar(
    month: str,
    user: dict = Depends(get_current_user),
    conn: sqlite3.Connection = Depends(db.get_db),
):
    rows = conn.execute(
        "SELECT DISTINCT date FROM sessions WHERE email = ? AND date LIKE ? ORDER BY date",
        (user["email"], f"{month}%"),
    ).fetchall()
    return {"dates": [r["date"] for r in rows]}


def _day_summary(day_sessions: list[dict]) -> dict:
    total_reps = sum(s["total_reps"] for s in day_sessions)
    all_sets = [st for s in day_sessions for st in s["sets"]]
    avg_form_score = (
        sum(st["form_score"] for st in all_sets) / len(all_sets) if all_sets else 0
    )
    return {
        "total_reps": total_reps,
        "avg_form_score": avg_form_score,
        "sets": all_sets,
    }


@app.get("/compare")
def compare(
    exercise_id: str,
    user: dict = Depends(get_current_user),
    conn: sqlite3.Connection = Depends(db.get_db),
):
    rows = conn.execute(
        "SELECT * FROM sessions WHERE email = ? AND exercise_id = ?",
        (user["email"], exercise_id),
    ).fetchall()
    my_sessions = [_row_session(r) for r in rows]
    dates = sorted({s["date"] for s in my_sessions}, reverse=True)
    today_str = date_cls.today().isoformat()

    today_dates = [d for d in dates if d == today_str]
    previous_dates = [d for d in dates if d < today_str]

    today = None
    if today_dates:
        today = _day_summary([s for s in my_sessions if s["date"] == today_dates[0]])

    previous = None
    if previous_dates:
        prev_date = previous_dates[0]
        previous = _day_summary([s for s in my_sessions if s["date"] == prev_date])
        previous["date"] = prev_date

    delta = None
    if today is not None and previous is not None:
        delta = {
            "total_reps": today["total_reps"] - previous["total_reps"],
            "avg_form_score": today["avg_form_score"] - previous["avg_form_score"],
        }

    return {"today": today, "previous": previous, "delta": delta}


def _is_image(data: bytes) -> bool:
    return imghdr.what(None, data) is not None


@app.post("/inference/pose")
async def inference_pose(
    frame: UploadFile = File(...),
    exercise_id: str = Form(...),
    user: dict = Depends(get_current_user),
):
    image_bytes = await frame.read()
    if not image_bytes or not _is_image(image_bytes):
        raise HTTPException(status_code=400, detail="invalid image")

    result = pose_estimator.get_estimator().estimate(image_bytes)
    detected = pose_eval.is_detected(result.keypoints)
    evaluation = pose_eval.evaluate(result.keypoints, exercise_id) if detected else None

    return {
        "detected": detected,
        "keypoints": result.keypoints,
        "evaluation": evaluation,
    }


# ---- 운동 프로그램 (세트/휴식) ----

EXERCISE_IDS = {e["id"] for e in EXERCISES}
EXERCISE_NAMES = {e["id"]: e["name"] for e in EXERCISES}


def _require_exercise(exercise_id: str) -> None:
    if exercise_id not in EXERCISE_IDS:
        raise HTTPException(status_code=404, detail="unknown exercise_id")


def _get_override(conn: sqlite3.Connection, email: str, exercise_id: str) -> Optional[dict]:
    row = conn.execute(
        "SELECT level, sets, reps, rest_sec FROM program_overrides WHERE email = ? AND exercise_id = ?",
        (email, exercise_id),
    ).fetchone()
    return db.row_to_dict(row)


@app.get("/me/programs")
def list_programs(
    user: dict = Depends(get_current_user),
    conn: sqlite3.Connection = Depends(db.get_db),
):
    rows = conn.execute(
        "SELECT exercise_id, level, sets, reps, rest_sec FROM program_overrides WHERE email = ?",
        (user["email"],),
    ).fetchall()
    return [dict(r) for r in rows]


@app.put("/me/programs/{exercise_id}")
def put_program(
    exercise_id: str,
    body: ProgramOverride,
    user: dict = Depends(get_current_user),
    conn: sqlite3.Connection = Depends(db.get_db),
):
    _require_exercise(exercise_id)
    v = body.model_dump()
    conn.execute(
        "INSERT INTO program_overrides (email, exercise_id, level, sets, reps, rest_sec) "
        "VALUES (?, ?, ?, ?, ?, ?) "
        "ON CONFLICT(email, exercise_id) DO UPDATE SET "
        "level = excluded.level, sets = excluded.sets, reps = excluded.reps, rest_sec = excluded.rest_sec",
        (user["email"], exercise_id, v["level"], v["sets"], v["reps"], v["rest_sec"]),
    )
    conn.commit()
    return {"exercise_id": exercise_id, **v}


@app.get("/me/plan")
def get_plan(
    exercise_id: str,
    level: Optional[str] = None,
    user: dict = Depends(get_current_user),
    conn: sqlite3.Connection = Depends(db.get_db),
):
    _require_exercise(exercise_id)
    if level is not None and level not in program.LEVELS:
        raise HTTPException(status_code=400, detail="unknown level")
    completed = conn.execute(
        "SELECT COUNT(*) AS n FROM sessions WHERE email = ? AND exercise_id = ?",
        (user["email"], exercise_id),
    ).fetchone()["n"]
    return program.resolve(
        exercise_id,
        level or program.DEFAULT_LEVEL,
        completed,
        _get_override(conn, user["email"], exercise_id),
    )


# ---- 문장 기반 분석 ----


def _previous_session(all_sessions: list[dict], session: dict) -> Optional[dict]:
    """같은 운동의 직전 세션. all_sessions는 started_at 오름차순."""
    earlier = [
        s
        for s in all_sessions
        if s["exercise_id"] == session["exercise_id"] and s["started_at"] < session["started_at"]
    ]
    return earlier[-1] if earlier else None


def _all_sessions(conn: sqlite3.Connection, email: str) -> list[dict]:
    # ponytail: 사용자의 전체 세션을 한 번에 읽는다. 세션당 이전 세션을 따로 조회하면
    # N+1이 된다. 수천 건이 쌓이면 exercise_id/기간으로 좁힐 것.
    rows = conn.execute(
        "SELECT * FROM sessions WHERE email = ? ORDER BY started_at", (email,)
    ).fetchall()
    return [_row_session(r) for r in rows]


def _analyze(session: dict, all_sessions: list[dict]) -> dict:
    return analysis.build(
        session,
        _previous_session(all_sessions, session),
        EXERCISE_NAMES.get(session["exercise_id"]),
    )


@app.get("/sessions/{session_id}/analysis")
def get_session_analysis(
    session_id: str,
    user: dict = Depends(get_current_user),
    conn: sqlite3.Connection = Depends(db.get_db),
):
    all_sessions = _all_sessions(conn, user["email"])
    session = next((s for s in all_sessions if s["id"] == session_id), None)
    if session is None:
        raise HTTPException(status_code=404, detail="session not found")
    return _analyze(session, all_sessions)


@app.get("/analysis")
def get_day_analysis(
    date: str,
    user: dict = Depends(get_current_user),
    conn: sqlite3.Connection = Depends(db.get_db),
):
    """캘린더에서 날짜를 탭했을 때 쓰는 단일 엔드포인트 — 그날 세션 + 각 세션 분석."""
    all_sessions = _all_sessions(conn, user["email"])
    day = [s for s in all_sessions if s["date"] == date]
    return {
        "date": date,
        "summary": analysis.day_summary(day),
        "sessions": [{**s, "analysis": _analyze(s, all_sessions)} for s in day],
    }

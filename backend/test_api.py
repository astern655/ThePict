import os
import tempfile
from datetime import date, timedelta

os.environ["HOHOWATT_DB"] = os.path.join(tempfile.gettempdir(), "hohowatt_test.db")

import pytest
from fastapi.testclient import TestClient

import db
import main

client = TestClient(main.app)


@pytest.fixture(autouse=True)
def reset_store():
    db.reset()
    yield


def register(email="user1@test.com", password="pw123"):
    r = client.post("/auth/register", json={"email": email, "password": password})
    assert r.status_code == 201
    return r.json()["token"]


def auth_headers(token):
    return {"Authorization": f"Bearer {token}"}


def test_register_duplicate_conflict():
    register("dup@test.com")
    r = client.post("/auth/register", json={"email": "dup@test.com", "password": "x"})
    assert r.status_code == 409


def test_login_wrong_password():
    register("login@test.com", "correct")
    r = client.post("/auth/login", json={"email": "login@test.com", "password": "wrong"})
    assert r.status_code == 401


def test_unauthenticated_requests_401():
    assert client.get("/me/profile").status_code == 401
    assert client.get("/sessions").status_code == 401
    assert client.get("/calendar?month=2026-07").status_code == 401
    assert client.get("/compare?exercise_id=squat").status_code == 401


def test_exercises_seed_no_auth_needed():
    r = client.get("/exercises")
    assert r.status_code == 200
    data = r.json()
    ids = {e["id"]: e for e in data}
    # AI 엔진이 분석하는 운동만 supported=True (ai/analysis/exercises/REGISTRY와 일치)
    assert ids["squat"]["supported"] is True
    assert len(ids["squat"]["steps"]) > 0
    assert ids["pushup"]["supported"] is True
    assert len(ids["pushup"]["steps"]) > 0
    assert ids["deadlift"]["supported"] is False
    assert ids["bench_press"]["supported"] is False
    assert ids["lunge"]["supported"] is False


def test_full_flow_profile_sessions_calendar_compare_and_isolation():
    token = register("flow@test.com")
    headers = auth_headers(token)

    # profile before onboarding: nulls
    r = client.get("/me/profile", headers=headers)
    assert r.status_code == 200
    body = r.json()
    assert body["email"] == "flow@test.com"
    assert body["gender"] is None

    # update profile
    r = client.put(
        "/me/profile",
        headers=headers,
        json={"gender": "female", "age": 28, "height_cm": 165.0, "weight_kg": 55.0, "goal": "체지방 감소"},
    )
    assert r.status_code == 200
    assert r.json()["age"] == 28

    today = date.today()
    yesterday = today - timedelta(days=1)

    # session on a previous day
    r = client.post(
        "/sessions",
        headers=headers,
        json={
            "exercise_id": "squat",
            "started_at": f"{yesterday.isoformat()}T09:00:00",
            "sets": [{"reps": 10, "form_score": 70}, {"reps": 10, "form_score": 80}],
        },
    )
    assert r.status_code == 201
    prev_session = r.json()
    assert prev_session["total_reps"] == 20
    assert prev_session["avg_form_score"] == 75

    # two sessions today (should be summed for compare)
    r = client.post(
        "/sessions",
        headers=headers,
        json={
            "exercise_id": "squat",
            "started_at": f"{today.isoformat()}T08:00:00",
            "sets": [{"reps": 12, "form_score": 90}],
        },
    )
    assert r.status_code == 201
    r = client.post(
        "/sessions",
        headers=headers,
        json={
            "exercise_id": "squat",
            "started_at": f"{today.isoformat()}T18:00:00",
            "sets": [{"reps": 8, "form_score": 100}],
        },
    )
    assert r.status_code == 201

    # sessions filtered by date
    r = client.get(f"/sessions?date={today.isoformat()}", headers=headers)
    assert r.status_code == 200
    assert len(r.json()) == 2

    r = client.get("/sessions", headers=headers)
    assert len(r.json()) == 3

    # calendar
    r = client.get(f"/calendar?month={today.strftime('%Y-%m')}", headers=headers)
    assert r.status_code == 200
    dates = r.json()["dates"]
    assert today.isoformat() in dates

    # compare
    r = client.get("/compare?exercise_id=squat", headers=headers)
    assert r.status_code == 200
    cmp = r.json()
    assert cmp["today"]["total_reps"] == 20  # 12 + 8
    assert cmp["today"]["avg_form_score"] == 95  # (90+100)/2
    assert cmp["previous"]["total_reps"] == 20
    assert cmp["previous"]["date"] == yesterday.isoformat()
    assert cmp["delta"]["total_reps"] == 0

    # --- user isolation ---
    token2 = register("other@test.com")
    headers2 = auth_headers(token2)

    r = client.get("/sessions", headers=headers2)
    assert r.json() == []

    r = client.get(f"/calendar?month={today.strftime('%Y-%m')}", headers=headers2)
    assert r.json()["dates"] == []

    r = client.get("/compare?exercise_id=squat", headers=headers2)
    body = r.json()
    assert body["today"] is None
    assert body["previous"] is None
    assert body["delta"] is None

    r = client.get("/me/profile", headers=headers2)
    assert r.json()["gender"] is None


def test_compare_no_data_returns_nulls():
    token = register("nodata@test.com")
    r = client.get("/compare?exercise_id=squat", headers=auth_headers(token))
    assert r.json() == {"today": None, "previous": None, "delta": None}


def test_delete_account_removes_sessions_and_token():
    token = register("del@test.com")
    headers = auth_headers(token)
    client.post(
        "/sessions",
        headers=headers,
        json={
            "exercise_id": "squat",
            "started_at": f"{date.today().isoformat()}T09:00:00",
            "sets": [{"reps": 10, "form_score": 70}],
        },
    )
    r = client.delete("/me", headers=headers)
    assert r.status_code == 204
    r = client.get("/me/profile", headers=headers)
    assert r.status_code == 401


def test_data_persists_across_new_connections():
    token = register("persist@test.com")
    headers = auth_headers(token)
    client.put("/me/profile", headers=headers, json={"gender": "male"})
    client.post(
        "/sessions",
        headers=headers,
        json={
            "exercise_id": "squat",
            "started_at": f"{date.today().isoformat()}T09:00:00",
            "sets": [{"reps": 10, "form_score": 70}],
        },
    )

    # brand-new connection, independent of whatever the request handlers used
    gen = db.get_db()
    conn = next(gen)
    try:
        user_row = conn.execute(
            "SELECT * FROM users WHERE email = ?", ("persist@test.com",)
        ).fetchone()
        assert user_row["gender"] == "male"
        session_row = conn.execute(
            "SELECT * FROM sessions WHERE email = ?", ("persist@test.com",)
        ).fetchone()
        assert session_row["total_reps"] == 10
    finally:
        conn.close()


def test_password_hashes_use_distinct_salts():
    register("saltA@test.com", "samepassword")
    register("saltB@test.com", "samepassword")
    gen = db.get_db()
    conn = next(gen)
    try:
        hash_a = conn.execute(
            "SELECT password_hash FROM users WHERE email = ?", ("saltA@test.com",)
        ).fetchone()["password_hash"]
        hash_b = conn.execute(
            "SELECT password_hash FROM users WHERE email = ?", ("saltB@test.com",)
        ).fetchone()["password_hash"]
    finally:
        conn.close()
    assert hash_a.startswith("pbkdf2_sha256$")
    assert hash_a != hash_b

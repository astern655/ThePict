import os
import tempfile
from datetime import date, timedelta

os.environ["HOHOWATT_DB"] = os.path.join(tempfile.gettempdir(), "hohowatt_test.db")

import pytest
from fastapi.testclient import TestClient

import db
import main
import program

client = TestClient(main.app)


@pytest.fixture(autouse=True)
def reset_store():
    db.reset()
    yield


def register(email="prog@test.com", password="pw123"):
    r = client.post("/auth/register", json={"email": email, "password": password})
    assert r.status_code == 201
    return {"Authorization": f"Bearer {r.json()['token']}"}


def log_sessions(headers, n, exercise_id="squat"):
    """완료 세션 n건을 서로 다른 날짜로 쌓는다."""
    base = date.today() - timedelta(days=n)
    for i in range(n):
        r = client.post(
            "/sessions",
            headers=headers,
            json={
                "exercise_id": exercise_id,
                "started_at": f"{(base + timedelta(days=i)).isoformat()}T09:00:00",
                "sets": [{"reps": 10, "form_score": 70}],
            },
        )
        assert r.status_code == 201


# ---- 프리셋 ----


def test_exercises_expose_presets_for_three_levels():
    data = {e["id"]: e for e in client.get("/exercises").json()}
    presets = data["squat"]["presets"]
    assert set(presets) == {"beginner", "intermediate", "advanced"}
    assert presets["beginner"] == {"sets": 2, "reps": 10, "rest_sec": 90}
    # 초급일수록 세트는 적고 휴식은 길다
    assert presets["beginner"]["sets"] < presets["advanced"]["sets"]
    assert presets["beginner"]["rest_sec"] > presets["advanced"]["rest_sec"]
    # 중량 복합관절은 휴식이 더 길다
    assert data["deadlift"]["presets"]["beginner"]["rest_sec"] > presets["beginner"]["rest_sec"]


def test_existing_exercise_fields_unchanged():
    data = {e["id"]: e for e in client.get("/exercises").json()}
    for key in ("id", "name", "target", "difficulty", "steps", "cautions", "supported"):
        assert key in data["squat"]


# ---- 점진 증가 ----


@pytest.mark.parametrize(
    "completed,sets,reps,source",
    [
        (0, 2, 10, "preset"),
        (2, 2, 10, "preset"),
        (3, 3, 10, "progression"),   # 3세션마다 +1세트
        (6, 4, 10, "progression"),
        (9, 4, 12, "progression"),   # 세트 상한(+2) 도달 후 반복수 +2
        (12, 4, 14, "progression"),
        (30, 4, 14, "progression"),  # 상한에서 멈춘다
    ],
)
def test_progression_steps(completed, sets, reps, source):
    plan = program.resolve("squat", "beginner", completed, None)
    assert (plan["sets"], plan["reps"], plan["source"]) == (sets, reps, source)
    assert plan["rest_sec"] == 90  # 휴식은 자동으로 줄지 않는다


def test_progression_is_per_exercise_and_reflected_in_plan():
    headers = register()
    log_sessions(headers, 3, "squat")
    log_sessions(headers, 1, "lunge")

    squat = client.get("/me/plan?exercise_id=squat", headers=headers).json()
    assert squat["completed_sessions"] == 3
    assert squat["sets"] == 3
    assert squat["source"] == "progression"
    assert "3세션" in squat["message"]

    lunge = client.get("/me/plan?exercise_id=lunge", headers=headers).json()
    assert lunge["completed_sessions"] == 1
    assert lunge["sets"] == 2
    assert lunge["next_step_in_sessions"] == 2


# ---- 개인 설정 오버라이드 ----


def test_override_beats_progression_field_by_field():
    headers = register()
    log_sessions(headers, 6, "squat")  # 점진증가로 4세트

    r = client.put("/me/programs/squat", headers=headers, json={"sets": 6})
    assert r.status_code == 200

    plan = client.get("/me/plan?exercise_id=squat", headers=headers).json()
    assert plan["sets"] == 6            # 개인 설정 우선
    assert plan["reps"] == 10           # 지정 안 한 필드는 점진증가 값
    assert plan["rest_sec"] == 90
    assert plan["source"] == "custom"
    assert plan["overridden_fields"] == ["sets"]


def test_override_level_changes_preset_base():
    headers = register()
    client.put("/me/programs/squat", headers=headers, json={"level": "advanced"})
    plan = client.get("/me/plan?exercise_id=squat", headers=headers).json()
    assert plan["level"] == "advanced"
    assert (plan["sets"], plan["reps"], plan["rest_sec"]) == (4, 15, 45)
    assert plan["source"] == "preset"  # level만 바꾼 건 값 오버라이드가 아니다


def test_override_can_be_cleared_and_listed():
    headers = register()
    client.put("/me/programs/squat", headers=headers, json={"sets": 6, "rest_sec": 30})
    assert client.get("/me/programs", headers=headers).json() == [
        {"exercise_id": "squat", "level": None, "sets": 6, "reps": None, "rest_sec": 30}
    ]

    client.put("/me/programs/squat", headers=headers, json={})  # 전체 대체 = 해제
    plan = client.get("/me/plan?exercise_id=squat", headers=headers).json()
    assert plan["source"] == "preset"
    assert plan["rest_sec"] == 90


def test_plan_validation_and_auth():
    headers = register()
    assert client.get("/me/plan?exercise_id=squat").status_code == 401
    assert client.get("/me/programs").status_code == 401
    assert client.put("/me/programs/squat", json={"sets": 3}).status_code == 401
    assert client.get("/me/plan?exercise_id=nope", headers=headers).status_code == 404
    assert client.get("/me/plan?exercise_id=squat&level=god", headers=headers).status_code == 400
    assert client.put("/me/programs/squat", headers=headers, json={"sets": 0}).status_code == 422
    assert client.put("/me/programs/nope", headers=headers, json={}).status_code == 404


def test_overrides_are_per_user_and_deleted_with_account():
    h1 = register("o1@test.com")
    h2 = register("o2@test.com")
    client.put("/me/programs/squat", headers=h1, json={"sets": 7})
    assert client.get("/me/programs", headers=h2).json() == []

    client.delete("/me", headers=h1)
    gen = db.get_db()
    conn = next(gen)
    try:
        assert conn.execute(
            "SELECT COUNT(*) FROM program_overrides WHERE email = ?", ("o1@test.com",)
        ).fetchone()[0] == 0
    finally:
        conn.close()

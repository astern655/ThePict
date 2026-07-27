import os
import tempfile
from datetime import date, timedelta

os.environ["HOHOWATT_DB"] = os.path.join(tempfile.gettempdir(), "hohowatt_test.db")

import pytest
from fastapi.testclient import TestClient

import db
import main
import pose_eval

client = TestClient(main.app)

RULES = pose_eval.RULES["squat"]


@pytest.fixture(autouse=True)
def reset_store():
    db.reset()
    yield


def register(email="ana@test.com"):
    r = client.post("/auth/register", json={"email": email, "password": "pw"})
    assert r.status_code == 201
    return {"Authorization": f"Bearer {r.json()['token']}"}


def checks(knee, hip, back):
    """pose_eval의 임계값으로 status를 계산해 실제 추론 결과와 같은 모양을 만든다."""
    spec = [
        ("knee_angle", knee, RULES["knee_angle_min"], RULES["knee_angle_max"]),
        ("hip_angle", hip, RULES["hip_angle_min"], RULES["hip_angle_max"]),
        ("back_angle", back, 0, RULES["back_angle_max"]),
    ]
    return [
        {"name": n, "value": v, "status": "ok" if lo <= v <= hi else "bad", "message": ""}
        for n, v, lo, hi in spec
    ]


def post_session(headers, day, sets, exercise_id="squat"):
    r = client.post(
        "/sessions",
        headers=headers,
        json={"exercise_id": exercise_id, "started_at": f"{day.isoformat()}T09:00:00", "sets": sets},
    )
    assert r.status_code == 201
    return r.json()


def analysis_of(headers, session_id):
    r = client.get(f"/sessions/{session_id}/analysis", headers=headers)
    assert r.status_code == 200
    return r.json()


TODAY = date.today()
YESTERDAY = TODAY - timedelta(days=1)


# ---- 잘한 점 / 못한 점 ----


def test_bad_joint_is_named_with_counts_and_range():
    headers = register()
    s = post_session(
        headers,
        TODAY,
        [
            {"reps": 10, "form_score": 66.7, "checks": checks(108, 85, 30)},
            {"reps": 10, "form_score": 66.7, "checks": checks(112, 88, 32)},
            {"reps": 10, "form_score": 100, "checks": checks(90, 85, 30)},
        ],
    )
    a = analysis_of(headers, s["id"])
    assert a["has_joint_data"] is True

    bad = " ".join(a["bad"])
    assert "무릎 각도" in bad
    assert "3세트 중 2세트" in bad
    assert "70~90°" in bad
    assert "얕게" in bad  # 범위 위로 벗어남 = 얕은 스쿼트

    good = " ".join(a["good"])
    assert "고관절 각도" in good and "3세트 전부" in good
    assert "허리 각도" in good

    # 다음에 할 것: 문제가 큰 항목을 콕 집어 구체적 지시
    assert len(a["next"]) == 1
    assert "무릎 각도" in a["next"][0]
    assert "허벅지가 바닥과 평행" in a["next"][0]


def test_all_good_session_has_no_bad_and_no_next():
    headers = register()
    s = post_session(headers, TODAY, [{"reps": 10, "form_score": 100, "checks": checks(85, 80, 20)}])
    a = analysis_of(headers, s["id"])
    assert a["bad"] == []
    assert a["next"] == []
    assert len(a["good"]) == 3


def test_too_deep_squat_gets_opposite_diagnosis():
    headers = register()
    s = post_session(headers, TODAY, [{"reps": 10, "form_score": 66.7, "checks": checks(50, 80, 20)}])
    a = analysis_of(headers, s["id"])
    assert "깊게" in a["bad"][0]
    assert "주저앉지 말고" in a["next"][0]


# ---- 이전 대비 변화와 이유 ----


def test_change_names_the_joint_and_the_cause():
    headers = register()
    post_session(headers, YESTERDAY, [{"reps": 10, "form_score": 66.7, "checks": checks(90, 80, 55)}])
    today = post_session(
        headers, TODAY, [{"reps": 10, "form_score": 100, "checks": checks(90, 80, 29)}]
    )
    a = analysis_of(headers, today["id"])
    change = " ".join(a["change"])
    assert "허리 각도" in change
    assert "55" in change and "29" in change
    assert "주 원인" in change
    assert "+33.3점" in change
    assert a["compared_with"]["date"] == YESTERDAY.isoformat()


def test_regression_is_reported_as_worse():
    headers = register()
    post_session(headers, YESTERDAY, [{"reps": 10, "form_score": 100, "checks": checks(90, 80, 20)}])
    today = post_session(
        headers, TODAY, [{"reps": 10, "form_score": 66.7, "checks": checks(90, 80, 60)}]
    )
    a = analysis_of(headers, today["id"])
    assert "멀어졌어요" in " ".join(a["change"])
    assert "하락" in " ".join(a["change"])


def test_first_session_says_so_instead_of_inventing_a_comparison():
    headers = register()
    s = post_session(headers, TODAY, [{"reps": 10, "form_score": 100, "checks": checks(85, 80, 20)}])
    a = analysis_of(headers, s["id"])
    assert a["change"] == []
    assert a["compared_with"] is None
    assert "비교할 이전 스쿼트 세션이 없어요" in " ".join(a["notes"])


def test_comparison_is_scoped_to_the_same_exercise():
    headers = register()
    post_session(headers, YESTERDAY, [{"reps": 10, "form_score": 50}], exercise_id="lunge")
    s = post_session(headers, TODAY, [{"reps": 10, "form_score": 100, "checks": checks(85, 80, 20)}])
    a = analysis_of(headers, s["id"])
    assert a["compared_with"] is None


# ---- 데이터 부족 (구세션 호환) ----


def test_legacy_session_without_checks_is_honest_not_fabricated():
    headers = register()
    s = post_session(headers, TODAY, [{"reps": 10, "form_score": 70}])
    a = analysis_of(headers, s["id"])
    assert a["has_joint_data"] is False
    assert a["good"] == [] and a["bad"] == [] and a["next"] == []
    assert "관절 판정 데이터가 없어서" in " ".join(a["notes"])


def test_legacy_previous_session_limits_comparison_to_scores():
    headers = register()
    post_session(headers, YESTERDAY, [{"reps": 10, "form_score": 70}])  # checks 없음
    today = post_session(
        headers, TODAY, [{"reps": 10, "form_score": 100, "checks": checks(85, 80, 20)}]
    )
    a = analysis_of(headers, today["id"])
    assert a["has_joint_data"] is True
    assert a["change"] == []
    note = " ".join(a["notes"])
    assert "원인까지는 비교할 수 없어요" in note
    assert "70" in note and "100" in note


def test_checks_are_optional_and_round_trip_through_storage():
    headers = register()
    posted = post_session(headers, TODAY, [{"reps": 5, "form_score": 100, "checks": checks(85, 80, 20)}])
    assert "checks" not in posted["sets"][0] or posted["sets"][0]["checks"]
    stored = client.get(f"/sessions?date={TODAY.isoformat()}", headers=headers).json()[0]
    assert stored["sets"][0]["checks"][0]["name"] == "knee_angle"
    assert stored["total_reps"] == 5  # 기존 필드 그대로


# ---- 캘린더 연동 ----


def test_day_analysis_returns_sessions_and_analyses_in_one_call():
    headers = register()
    post_session(headers, YESTERDAY, [{"reps": 10, "form_score": 66.7, "checks": checks(108, 80, 20)}])
    post_session(headers, TODAY, [{"reps": 10, "form_score": 100, "checks": checks(90, 80, 20)}])
    post_session(headers, TODAY, [{"reps": 8, "form_score": 100, "checks": checks(88, 80, 22)}])

    r = client.get(f"/analysis?date={TODAY.isoformat()}", headers=headers)
    assert r.status_code == 200
    body = r.json()
    assert body["date"] == TODAY.isoformat()
    assert "2개 세션, 총 18회" in body["summary"][0]
    assert len(body["sessions"]) == 2
    first = body["sessions"][0]
    assert first["total_reps"] == 10          # 세션 필드 그대로 포함
    assert first["analysis"]["good"]          # 분석도 같이
    assert "무릎 각도" in " ".join(first["analysis"]["change"])


def test_day_analysis_empty_day():
    headers = register()
    body = client.get("/analysis?date=1999-01-01", headers=headers).json()
    assert body["sessions"] == []
    assert "기록된 운동이 없어요" in body["summary"][0]


def test_analysis_auth_and_ownership():
    headers = register("owner@test.com")
    other = register("other2@test.com")
    s = post_session(headers, TODAY, [{"reps": 10, "form_score": 100}])

    assert client.get(f"/sessions/{s['id']}/analysis").status_code == 401
    assert client.get("/analysis?date=2026-01-01").status_code == 401
    # 남의 세션은 조회 불가
    assert client.get(f"/sessions/{s['id']}/analysis", headers=other).status_code == 404
    assert client.get("/sessions/nonexistent/analysis", headers=headers).status_code == 404

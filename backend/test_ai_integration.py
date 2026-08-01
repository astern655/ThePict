"""백엔드 ↔ AI 엔진(`ai/`) 접합부 테스트.

ML 런타임 없이도 돌아야 하므로, 무거운 의존성이 필요한 것은 skip으로 빠진다.
대신 '리포트 → 세트 변환'과 '임계값 동기화'는 의존성 없이 전부 검증한다.
"""

import os
import tempfile

os.environ.setdefault("HOHOWATT_DB", os.path.join(tempfile.gettempdir(), "hohowatt_test.db"))

import pytest
from fastapi.testclient import TestClient

import ai_bridge
import analysis
import db
import main
import pose_eval
import video_analysis

client = TestClient(main.app)


@pytest.fixture(autouse=True)
def reset_store():
    db.reset()
    yield


def register_and_login(email="video@test.com", password="pw123"):
    r = client.post("/auth/register", json={"email": email, "password": password})
    assert r.status_code == 201
    return r.json()["token"]


def auth_headers(token):
    return {"Authorization": f"Bearer {token}"}


# ---- 임계값 동기화 -------------------------------------------------------
# pose_eval.RULES가 AI 엔진의 기준을 복사해 들고 있다. 엔진 쪽만 튜닝하고
# 여기를 잊으면 사용자에게 틀린 목표 범위를 안내하게 되므로 테스트로 묶는다.


def test_rules_match_ai_engine_thresholds():
    try:
        config = ai_bridge.load_config()
    except ai_bridge.EngineUnavailable:
        pytest.skip("ai 패키지 없음")
    rules = pose_eval.RULES["squat"]
    assert rules["squat_depth_max"] == config.SQUAT_GOOD_DEPTH_ANGLE
    assert rules["torso_shin_diff_max"] == config.SQUAT_TORSO_SHIN_DIFF_WARN

    pushup = pose_eval.RULES["pushup"]
    assert pushup["pushup_depth_max"] == config.PUSHUP_GOOD_DEPTH_ANGLE
    assert pushup["body_line_dev_max"] == config.PUSHUP_BODY_LINE_WARN


def test_video_checks_have_analysis_metadata():
    """video_analysis가 내는 check 이름을 analysis.py가 문장으로 바꿀 수 있어야 한다.

    이름·범위 키·RULES가 운동별로 다 이어져 있어야 리포트가 문장이 된다.
    하나라도 빠지면 사용자에게 항목이 조용히 사라진다.
    """
    for exercise_id, spec in video_analysis.EXERCISE_CHECKS.items():
        for name in (spec["depth_check"], spec["form_check"]):
            assert name in analysis.CHECK_META, (exercise_id, name)
            _, hi_key = analysis.CHECK_META[name]["range"]
            assert hi_key in pose_eval.RULES[exercise_id], (exercise_id, hi_key)


def test_supported_exercises_match_engine_registry():
    """백엔드가 supported=True로 광고하는 운동 = 엔진이 실제로 분석하는 운동."""
    advertised = {e["id"] for e in main.EXERCISES if e["supported"]}
    assert advertised == video_analysis.SUPPORTED_EXERCISES

    try:
        engine = ai_bridge.load_engine()
    except ai_bridge.EngineUnavailable:
        pytest.skip("ai 패키지 없음")
    from ai.analysis.exercises import available_exercises

    assert video_analysis.SUPPORTED_EXERCISES == set(available_exercises())
    assert engine is not None


def test_pushup_has_no_frame_level_evaluation():
    """/inference/pose(프레임 단위)는 스쿼트 전용이다. 푸시업엔 지어내지 않는다."""
    result = pose_eval.evaluate([], "pushup")
    assert result["verdict"] == "unsupported"
    assert result["checks"] == []


# ---- 리포트 → 세트 변환 --------------------------------------------------


def _report(rep_verdicts, issues):
    return {
        "rep_count": len(rep_verdicts),
        "rep_verdicts": [
            {"rep_index": i + 1, "verdict": v} for i, v in enumerate(rep_verdicts)
        ],
        "issues": issues,
    }


def _issue(rep, code, severity, measured):
    return {"rep_index": rep, "code": code, "severity": severity, "measured": measured}


def test_to_set_scores_all_correct_reps_at_100():
    report = _report(
        ["correct", "correct"],
        [
            _issue(1, "good_depth", "good", 90.0),
            _issue(2, "good_depth", "good", 92.0),
        ],
    )
    s = video_analysis.to_set(report)
    assert s == {
        "reps": 2,
        "form_score": 100.0,
        "checks": [
            {"name": "squat_depth", "value": 91.0, "status": "ok", "message": ""},
        ],
    }


def test_to_set_averages_verdict_scores_and_flags_bad_depth():
    report = _report(
        ["correct", "incorrect"],
        [
            _issue(1, "good_depth", "good", 90.0),
            _issue(2, "very_shallow_depth", "error", 130.0),
        ],
    )
    s = video_analysis.to_set(report)
    assert s["form_score"] == 65.0  # (100 + 30) / 2
    depth = next(c for c in s["checks"] if c["name"] == "squat_depth")
    assert depth["status"] == "bad"
    assert depth["value"] == 110.0


def test_to_set_reports_torso_only_when_engine_measured_it():
    """정상 rep은 상체 측정값을 남기지 않는다 — 재지 않은 값을 지어내면 안 된다."""
    clean = video_analysis.to_set(
        _report(["correct"], [_issue(1, "good_depth", "good", 90.0)])
    )
    assert [c["name"] for c in clean["checks"]] == ["squat_depth"]

    leaning = video_analysis.to_set(
        _report(
            ["needs_work"],
            [
                _issue(1, "good_depth", "good", 90.0),
                _issue(1, "torso_lean", "warning", 30.0),
            ],
        )
    )
    torso = next(c for c in leaning["checks"] if c["name"] == "torso_shin_diff")
    assert torso == {
        "name": "torso_shin_diff",
        "value": 30.0,
        "status": "bad",
        "message": "1회차에서 상체가 과하게 앞으로 접혔습니다",
    }


def test_to_set_handles_zero_reps():
    s = video_analysis.to_set(_report([], []))
    assert s == {"reps": 0, "form_score": 0.0, "checks": []}


def test_analysis_builds_sentences_from_video_checks():
    """영상 분석이 만든 세트가 기존 문장 분석 경로를 그대로 탄다."""
    video_set = video_analysis.to_set(
        _report(
            ["needs_work"],
            [
                _issue(1, "shallow_depth", "warning", 115.0),
                _issue(1, "torso_lean", "warning", 30.0),
            ],
        )
    )
    session = {
        "id": "s1",
        "exercise_id": "squat",
        "date": "2026-07-22",
        "avg_form_score": video_set["form_score"],
        "sets": [video_set],
    }
    result = analysis.build(session, None, "스쿼트")
    assert result["has_joint_data"] is True
    assert any("앉은 깊이" in b for b in result["bad"])
    assert any("상체 앞숙임" in b for b in result["bad"])
    assert result["next"]  # 교정 지시가 최소 하나는 나온다


# ---- 실측/더미 구분 ------------------------------------------------------
# 앱이 "이 판정이 진짜 측정인가"를 알 수 있어야 한다. 이 필드가 없으면 stub이
# 지어낸 좌표로 만든 교정 지시가 실측인 양 사용자에게 나간다.

PNG_BYTES = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06"
    b"\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00"
    b"\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)


def test_pose_response_marks_stub_output_as_not_measured(monkeypatch):
    import pose_estimator

    monkeypatch.delenv("POSE_ESTIMATOR", raising=False)
    monkeypatch.setattr(pose_estimator, "_estimator_cache", None)
    token = register_and_login("stub@test.com")
    r = client.post(
        "/inference/pose",
        headers=auth_headers(token),
        data={"exercise_id": "squat"},
        files={"frame": ("frame.png", PNG_BYTES, "image/png")},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["estimator"] == "stub"
    assert body["measured"] is False


def test_stub_and_yolo_disagree_on_measured_flag():
    """플래그가 상수로 굳지 않았는지 — 두 추정기가 서로 다른 값을 내야 의미가 있다."""
    import pose_estimator

    assert pose_estimator.StubPoseEstimator.measures_real_image is False
    assert pose_estimator.YoloPoseEstimator.measures_real_image is True


# ---- 점수 없음 vs 0점 ----------------------------------------------------
# 자세를 재지 않은 세트는 점수가 없다. 0점으로 치면 측정하지 않은 사람의 추세가
# 바닥으로 끌려가고, "지난 세션과 같은 0점"이라는 헛소리가 나간다.


def test_unmeasured_sets_are_excluded_from_average():
    token = register_and_login("noscore@test.com")
    r = client.post(
        "/sessions",
        headers=auth_headers(token),
        json={
            "exercise_id": "squat",
            "started_at": "2026-07-22T10:00:00",
            "sets": [{"reps": 10}, {"reps": 10, "form_score": 80.0}],
        },
    )
    assert r.status_code == 201
    # 미측정 세트를 0점으로 넣었다면 40.0이 됐을 것이다.
    assert r.json()["avg_form_score"] == 80.0


def test_fully_unmeasured_session_reports_no_score():
    token = register_and_login("noscore2@test.com")
    session = client.post(
        "/sessions",
        headers=auth_headers(token),
        json={
            "exercise_id": "squat",
            "started_at": "2026-07-22T11:00:00",
            "sets": [{"reps": 10}, {"reps": 8}],
        },
    ).json()
    # 자세를 하나도 안 쟀으면 세션 점수는 0이 아니라 None이다(/sessions와 /analysis 일치).
    assert session["avg_form_score"] is None

    a = client.get(f"/sessions/{session['id']}/analysis", headers=auth_headers(token)).json()
    assert a["has_score"] is False
    assert a["avg_form_score"] is None
    # 점수 문장을 지어내지 않는다.
    assert not any("점" in line and "평균 점수" in line for line in a["change"])


def test_sessions_and_analysis_agree_on_missing_score():
    """미측정 세션에서 /sessions와 /analysis가 같은 None을 내야 한다.

    예전엔 /sessions는 0, /analysis는 None을 줘서 홈 화면이 0을 실점수로 집계했다.
    """
    token = register_and_login("agree@test.com")
    session = client.post(
        "/sessions",
        headers=auth_headers(token),
        json={
            "exercise_id": "squat",
            "started_at": "2026-07-22T09:00:00",
            "sets": [{"reps": 10}],
        },
    ).json()
    listed = client.get("/sessions", headers=auth_headers(token)).json()[0]
    analysis_out = client.get(
        f"/sessions/{session['id']}/analysis", headers=auth_headers(token)
    ).json()
    assert session["avg_form_score"] is None
    assert listed["avg_form_score"] is None
    assert analysis_out["avg_form_score"] is None


def test_day_summary_says_no_score_when_nothing_measured():
    token = register_and_login("noscore3@test.com")
    client.post(
        "/sessions",
        headers=auth_headers(token),
        json={
            "exercise_id": "squat",
            "started_at": "2026-07-22T12:00:00",
            "sets": [{"reps": 12}],
        },
    )
    day = client.get("/analysis", params={"date": "2026-07-22"}, headers=auth_headers(token)).json()
    assert day["summary"] == ["1개 세션, 총 12회를 했어요. 자세를 측정한 기록이 없어 점수는 없습니다."]


def test_measured_session_still_reports_its_score():
    """미측정 처리가 정상 경로를 망가뜨리지 않았는지."""
    token = register_and_login("scored@test.com")
    session = client.post(
        "/sessions",
        headers=auth_headers(token),
        json={
            "exercise_id": "squat",
            "started_at": "2026-07-22T13:00:00",
            "sets": [{"reps": 10, "form_score": 90.0}],
        },
    ).json()
    assert session["avg_form_score"] == 90.0
    a = client.get(f"/sessions/{session['id']}/analysis", headers=auth_headers(token)).json()
    assert a["has_score"] is True
    assert a["avg_form_score"] == 90.0


# ---- 엔드포인트 ----------------------------------------------------------


def test_video_endpoint_requires_auth():
    r = client.post(
        "/inference/video",
        data={"exercise_id": "squat"},
        files={"video": ("clip.mp4", b"\x00\x01", "video/mp4")},
    )
    assert r.status_code == 401


def test_video_endpoint_rejects_empty_upload():
    token = register_and_login("video2@test.com")
    r = client.post(
        "/inference/video",
        headers=auth_headers(token),
        data={"exercise_id": "squat"},
        files={"video": ("clip.mp4", b"", "video/mp4")},
    )
    assert r.status_code == 400


def test_video_endpoint_rejects_unsupported_exercise():
    token = register_and_login("video3@test.com")
    r = client.post(
        "/inference/video",
        headers=auth_headers(token),
        data={"exercise_id": "deadlift"},
        files={"video": ("clip.mp4", b"\x00\x01", "video/mp4")},
    )
    assert r.status_code == 400


def test_video_endpoint_rejects_garbage_video():
    """의존성이 없으면 503, 있으면 열 수 없는 파일이라 400. 500은 어느 쪽도 아니다."""
    token = register_and_login("video4@test.com")
    r = client.post(
        "/inference/video",
        headers=auth_headers(token),
        data={"exercise_id": "squat"},
        files={"video": ("clip.mp4", b"not a video at all", "video/mp4")},
    )
    assert r.status_code in (400, 503)

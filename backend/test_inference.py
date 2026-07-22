import base64
import os
import tempfile

os.environ.setdefault("HOHOWATT_DB", os.path.join(tempfile.gettempdir(), "hohowatt_test.db"))

import pytest
from fastapi.testclient import TestClient

import ai_bridge
import db
import main
import pose_estimator

client = TestClient(main.app)

# minimal valid 1x1 transparent PNG
PNG_BYTES = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)


@pytest.fixture(autouse=True)
def reset_store():
    db.reset()
    yield


@pytest.fixture(autouse=True)
def reset_estimator_cache():
    pose_estimator._estimator_cache = None
    yield
    pose_estimator._estimator_cache = None


def register_and_login(email="pose@test.com", password="pw123"):
    r = client.post("/auth/register", json={"email": email, "password": password})
    assert r.status_code == 201
    return r.json()["token"]


def auth_headers(token):
    return {"Authorization": f"Bearer {token}"}


def test_valid_frame_returns_full_schema():
    token = register_and_login()
    r = client.post(
        "/inference/pose",
        headers=auth_headers(token),
        data={"exercise_id": "squat"},
        files={"frame": ("frame.png", PNG_BYTES, "image/png")},
    )
    assert r.status_code == 200
    body = r.json()
    assert isinstance(body["detected"], bool)
    assert len(body["keypoints"]) == 17
    for kp in body["keypoints"]:
        assert set(kp.keys()) == {"name", "x", "y", "confidence"}
    if body["detected"]:
        assert body["evaluation"]["exercise_id"] == "squat"
        assert "form_score" in body["evaluation"]
        assert "checks" in body["evaluation"]
    else:
        assert body["evaluation"] is None


def test_unsupported_exercise_verdict():
    token = register_and_login("pose2@test.com")
    r = client.post(
        "/inference/pose",
        headers=auth_headers(token),
        data={"exercise_id": "deadlift"},
        files={"frame": ("frame.png", PNG_BYTES, "image/png")},
    )
    assert r.status_code == 200
    body = r.json()
    if body["detected"]:
        assert body["evaluation"]["verdict"] == "unsupported"


def test_empty_frame_is_400():
    token = register_and_login("pose3@test.com")
    r = client.post(
        "/inference/pose",
        headers=auth_headers(token),
        data={"exercise_id": "squat"},
        files={"frame": ("frame.png", b"", "image/png")},
    )
    assert r.status_code == 400


def test_non_image_frame_is_400():
    token = register_and_login("pose4@test.com")
    r = client.post(
        "/inference/pose",
        headers=auth_headers(token),
        data={"exercise_id": "squat"},
        files={"frame": ("frame.txt", b"not an image, just text", "text/plain")},
    )
    assert r.status_code == 400


def test_unauthenticated_is_401():
    r = client.post(
        "/inference/pose",
        data={"exercise_id": "squat"},
        files={"frame": ("frame.png", PNG_BYTES, "image/png")},
    )
    assert r.status_code == 401


def test_get_estimator_defaults_to_stub_and_caches(monkeypatch):
    monkeypatch.delenv("POSE_ESTIMATOR", raising=False)
    est1 = pose_estimator.get_estimator()
    est2 = pose_estimator.get_estimator()
    assert isinstance(est1, pose_estimator.StubPoseEstimator)
    assert est1 is est2  # cached


def test_get_estimator_yolo_uses_ai_engine_or_reports_missing_deps(monkeypatch):
    """yolo를 고르면 저장소의 AI 엔진에 연결된다.

    ML 의존성이 없는 환경(CI 백엔드 잡 등)에서는 조용히 스텁으로 떨어지지 않고
    EngineUnavailable로 명확히 실패해야 한다 — 더미 좌표로 자세를 판정했다는
    사실을 아무도 모르는 상태가 가장 나쁘다.
    """
    monkeypatch.setenv("POSE_ESTIMATOR", "yolo")
    try:
        est = pose_estimator.get_estimator()
    except ai_bridge.EngineUnavailable:
        pytest.skip("AI 엔진 의존성 미설치 — 설치 환경에서만 검증한다")
    assert isinstance(est, pose_estimator.YoloPoseEstimator)

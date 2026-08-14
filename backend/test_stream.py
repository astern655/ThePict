"""실시간 스트리밍 WS(`/inference/stream`) 테스트.

실제 YOLO·cv2 는 느리고 무거우며 이 환경엔 설치돼 있지 않을 수 있어, detector 와
decode 만 가짜로 주입한다(analyzer 는 진짜를 그대로 돌린다). 주입은 이 테스트
파일 안에서만 일어나며 프로덕션 경로엔 새지 않는다.
"""
import os
import tempfile

os.environ.setdefault("HOHOWATT_DB", os.path.join(tempfile.gettempdir(), "hohowatt_test.db"))

import pytest
from fastapi.testclient import TestClient

import db
import main
import stream_session
from ai.pose.keypoints import Keypoint  # stream_session import 가 sys.path 를 세팅함

client = TestClient(main.app)


@pytest.fixture(autouse=True)
def reset_store():
    db.reset()
    yield


def register(email="stream@test.com", password="pw123"):
    r = client.post("/auth/register", json={"email": email, "password": password})
    assert r.status_code == 201
    return r.json()["token"]


class FakeDetector:
    """실제 YOLO 대신. 매 프레임 같은 사람(관절 17개)을 돌려준다."""

    def reset(self):
        pass

    def detect(self, frame):
        return [Keypoint(x=100.0 + i, y=200.0 + i, confidence=0.9) for i in range(17)]


class NoPersonDetector:
    def reset(self):
        pass

    def detect(self, frame):
        return None


def _inject(monkeypatch, detector):
    """StreamSession 을 detector/decode 주입 버전으로 바꾼다(analyzer 는 진짜)."""

    def factory(exercise_id):
        # decode 는 cv2 없이 non-None 프레임을 흉내내는 센티넬을 돌려준다.
        return stream_session.StreamSession(
            exercise_id, detector=detector, decode=lambda b: object()
        )

    monkeypatch.setattr(main.stream_session, "StreamSession", factory)


def test_stream_happy_path(monkeypatch):
    _inject(monkeypatch, FakeDetector())
    token = register()
    with client.websocket_connect("/inference/stream") as ws:
        ws.send_json({"type": "start", "token": token, "exercise_id": "squat"})
        assert ws.receive_json() == {"type": "ready"}

        for _ in range(5):
            ws.send_bytes(b"fake-jpeg-bytes")
            msg = ws.receive_json()
            assert msg["type"] == "frame"
            assert set(msg.keys()) == {
                "type", "person", "rep_count", "phase", "last_verdict", "warn",
            }
            assert len(msg["person"]) == 17
            assert set(msg["person"][0].keys()) == {"name", "x", "y", "confidence"}
            assert msg["phase"] in ("UP", "DOWN")
            assert isinstance(msg["rep_count"], int)
            assert msg["warn"] is None

        ws.send_json({"type": "stop"})
        result = ws.receive_json()
        assert result["type"] == "result"

        s = result["set"]
        assert set(s.keys()) == {"reps", "form_score", "checks"}
        assert isinstance(s["reps"], int)
        assert isinstance(s["form_score"], (int, float))
        assert isinstance(s["checks"], list)
        assert "rep_verdicts" in result["report"]


def test_stream_no_person_warns(monkeypatch):
    _inject(monkeypatch, NoPersonDetector())
    token = register()
    with client.websocket_connect("/inference/stream") as ws:
        ws.send_json({"type": "start", "token": token, "exercise_id": "squat"})
        assert ws.receive_json() == {"type": "ready"}
        ws.send_bytes(b"fake-jpeg-bytes")
        msg = ws.receive_json()
        assert msg["type"] == "frame"
        assert msg["person"] is None
        assert msg["warn"] == "no_person"


def test_stream_bad_frame(monkeypatch):
    _inject(monkeypatch, FakeDetector())
    token = register()
    with client.websocket_connect("/inference/stream") as ws:
        ws.send_json({"type": "start", "token": token, "exercise_id": "squat"})
        assert ws.receive_json() == {"type": "ready"}
        ws.send_bytes(b"")  # 빈 프레임 → bad_frame
        assert ws.receive_json() == {"type": "error", "code": "bad_frame"}


def test_stream_auth_failed():
    with client.websocket_connect("/inference/stream") as ws:
        ws.send_json({"type": "start", "token": "bogus-token", "exercise_id": "squat"})
        assert ws.receive_json() == {"type": "error", "code": "auth_failed"}


def test_stream_unsupported_exercise():
    token = register()
    with client.websocket_connect("/inference/stream") as ws:
        ws.send_json({"type": "start", "token": token, "exercise_id": "deadlift"})
        assert ws.receive_json() == {"type": "error", "code": "unsupported_exercise"}

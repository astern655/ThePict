"""실시간 스트리밍 자세 판정 — 연결 하나 = 세션 하나.

`/inference/video` 는 영상 파일 한 편을 통째로 엔진에 넘긴다. 여기서는 브라우저가
프레임을 한 장씩 보내오는 것을 그대로 받아, `ai/` 의 렙카운팅을 프레임 단위로
돌린다. 엔진의 `analyze_video` 루프(engine.py)가 하던 일(detect → analyzer.update)을
연결 수명 동안 이어서 하는 셈이라, 종료 시 나오는 리포트는 영상 분석과 같은
`to_set()` 으로 낮춰져 `/sessions` 스키마와 바이트 단위로 같은 세트가 된다.

`ai/` 는 재사용만 한다(한 줄도 바꾸지 않는다). detector/decode 는 생성자에서
주입 가능해, 테스트가 실제 YOLO·cv2 없이 analyzer 경로만 검증할 수 있다.
"""
from __future__ import annotations

import time

import ai_bridge
import video_analysis
from pose_eval import KEYPOINT_NAMES

# create_analyzer 는 최상단에서 import 하지 않는다 — 그 import 가 ai/__init__.py 를 거쳐
# opencv/ultralytics 를 강제로 끌어와, 의존성이 없으면 이 모듈을 import 하는 것만으로
# 서버 전체가 안 뜬다(회귀). 실제 스트림이 열릴 때 ai_bridge.load_create_analyzer() 로
# 지연 로드하고, 없으면 EngineUnavailable 로 바꾼다(video 경로의 503과 같은 정책).

# 벽시계에서 프레임 번호를 파생할 때 기준으로 삼는 명목 프레임률.
# 전송률이 들쭉날쭉해도 유실 임계(초 단위)가 정확히 걸리도록, 단순 +1 대신
# 경과 시간 × 이 값으로 프레임 번호를 만든다. analyzer 의 fps 도 같은 값으로 둬야
# rep 시각(초)과 유실 판정이 서로 어긋나지 않는다.
NOMINAL_FPS = 15.0


class BadFrame(ValueError):
    """디코딩 못 하거나 빈 프레임. 호출부(WS)가 bad_frame 오류로 바꾼다."""


def _cv2_decode(jpeg_bytes: bytes):
    """JPEG 바이트 → BGR 프레임(np.ndarray). 못 읽으면 None.

    cv2 는 무거운 AI 의존성이라 실제 프레임이 올 때만 import 한다(pose_estimator 와 동일).
    """
    import cv2
    import numpy as np

    return cv2.imdecode(np.frombuffer(jpeg_bytes, np.uint8), cv2.IMREAD_COLOR)


def _load_detector(exercise_id: str):
    """운동에 맞는 실제 YOLO detector. 엔진 의존성이 없으면 EngineUnavailable."""
    PoseDetector = ai_bridge.load_detector_class()
    config = ai_bridge.load_config()
    return PoseDetector(config.pose_model_for(exercise_id))


def _person_to_json(person) -> list[dict] | None:
    """detect() 의 Person(관절 17개) → 전송용 dict 목록. 사람이 없으면 None.

    좌표는 보낸 프레임의 픽셀 좌표 그대로다(프런트가 스켈레톤을 그린다).
    `/inference/pose` 와 같은 `{name, x, y, confidence}` 스키마를 재사용한다.
    """
    if person is None:
        return None
    return [
        {"name": name, "x": kp.x, "y": kp.y, "confidence": kp.confidence}
        for name, kp in zip(KEYPOINT_NAMES, person)
    ]


class StreamSession:
    """연결 하나의 실시간 판정 상태를 보유한다.

    detector 는 연결당 인스턴스 1개(대상 추적 상태를 가지므로) — 시작 시 reset().
    detector/decode 를 주입하지 않으면 실제 YOLO·cv2 를 쓴다(프로덕션 경로).
    """

    def __init__(self, exercise_id: str, fps: float = NOMINAL_FPS, *, detector=None, decode=None):
        self._exercise_id = exercise_id
        create_analyzer = ai_bridge.load_create_analyzer()  # 지연 로드(엔진 없으면 EngineUnavailable)
        self._analyzer = create_analyzer(exercise_id, fps=fps)
        self._detector = detector if detector is not None else _load_detector(exercise_id)
        self._detector.reset()
        self._decode = decode if decode is not None else _cv2_decode
        self._t0: float | None = None  # 첫 프레임 도착 시각(벽시계 기준점)

    def feed(self, jpeg_bytes: bytes) -> dict:
        """프레임 한 장을 판정해 회신 dict 를 만든다.

        순간(프레임 단위) 자세 판정은 존재하지 않는다 — 자세 판정은 rep 완료 시점에만
        계산되므로, 실시간 색은 `last_verdict`(직전 완료 rep 의 판정)로 표시한다.
        """
        if not jpeg_bytes:
            raise BadFrame("empty frame")
        frame = self._decode(jpeg_bytes)
        if frame is None:
            raise BadFrame("undecodable frame")

        now = time.monotonic()
        if self._t0 is None:
            self._t0 = now
        frame_index = round((now - self._t0) * NOMINAL_FPS)

        person = self._detector.detect(frame)
        self._analyzer.update(person, frame_index)

        report = self._analyzer.report
        rep_count = report.rep_count
        return {
            "person": _person_to_json(person),
            "rep_count": rep_count,
            "phase": self._analyzer.state,
            "last_verdict": report.rep_verdict(rep_count).value if rep_count > 0 else None,
            "warn": "no_person" if person is None else None,
        }

    def finish(self) -> dict:
        """스트림 종료 → 세트 하나 산출. `/inference/video` 와 같은 to_set() 을 쓴다."""
        report = self._analyzer.finalize().to_dict()
        # 서버 로컬 경로라 클라이언트에 흘리지 않는다(스트림은 애초에 만들지도 않는다).
        report.pop("annotated_video_path", None)
        return {"set": video_analysis.to_set(report, self._exercise_id), "report": report}

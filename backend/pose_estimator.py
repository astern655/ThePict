"""Model adapter boundary (D4). Swap the estimator without touching the API layer."""

import os
import random
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

import ai_bridge
from pose_eval import KEYPOINT_NAMES


@dataclass
class PoseResult:
    keypoints: list[dict] = field(default_factory=list)  # [{name, x, y, confidence}] x17


class PoseEstimator(ABC):
    @abstractmethod
    def estimate(self, image_bytes: bytes) -> PoseResult:
        """Run pose estimation on a single image and return COCO-17 keypoints
        in pixel coordinates (x, y) with a 0..1 confidence per point."""
        raise NotImplementedError


class StubPoseEstimator(PoseEstimator):
    """Deterministic, plausible-looking keypoints for local dev / tests
    without a real model. Not tied to actual image content."""

    def estimate(self, image_bytes: bytes) -> PoseResult:
        if not image_bytes:
            raise ValueError("empty image")
        # deterministic per-call "randomness" seeded off the payload so repeated
        # calls with the same bytes return the same stub result
        rng = random.Random(len(image_bytes))
        base_x, base_y = 320.0, 240.0
        keypoints = []
        for i, name in enumerate(KEYPOINT_NAMES):
            keypoints.append({
                "name": name,
                "x": base_x + rng.uniform(-100, 100) + i * 2,
                "y": base_y + rng.uniform(-150, 150) + i * 5,
                "confidence": rng.uniform(0.6, 0.95),
            })
        return PoseResult(keypoints=keypoints)


class YoloPoseEstimator(PoseEstimator):
    """저장소의 AI 엔진(`ai.pose.detector.PoseDetector`)을 감싼 실제 어댑터.

    엔진은 COCO-17을 표준 순서 그대로 돌려주므로 `KEYPOINT_NAMES` 와 zip만 하면
    이 계층의 `[{name, x, y, confidence}, ...]` 스키마가 된다.

    detector는 인스턴스에 물려 재사용한다 — YOLO 가중치 로딩은 초 단위로 비싸서
    요청마다 새로 만들면 안 된다(`get_estimator()` 가 인스턴스를 캐싱한다).
    """

    def __init__(self):
        PoseDetector = ai_bridge.load_detector_class()
        # 가중치 경로가 없으면 엔진 기본값(ai/config.POSE_MODEL, 없으면 자동 다운로드).
        weights = os.environ.get("YOLO_POSE_WEIGHTS")
        self._detector = PoseDetector(weights) if weights else PoseDetector()

    def estimate(self, image_bytes: bytes) -> PoseResult:
        if not image_bytes:
            raise ValueError("empty image")
        import cv2
        import numpy as np

        frame = cv2.imdecode(np.frombuffer(image_bytes, np.uint8), cv2.IMREAD_COLOR)
        if frame is None:
            raise ValueError("undecodable image")

        # /inference/pose는 무상태 단일 프레임 API다. detector의 "직전 프레임과 가장
        # 가까운 사람을 따라가기"는 요청 간에 사용자가 섞이면 오히려 엉뚱한 사람을
        # 고르게 하므로 매번 초기화한다. 프레임 간 추적이 필요한 경로는 영상 전체를
        # 한 번에 넘기는 /inference/video(video_analysis.py)다.
        self._detector.reset()
        person = self._detector.detect(frame)
        if person is None:
            # 사람이 없으면 빈 목록 — 호출부의 pose_eval.is_detected()가 False로 본다.
            return PoseResult(keypoints=[])
        return PoseResult(keypoints=[
            {"name": name, "x": kp.x, "y": kp.y, "confidence": kp.confidence}
            for name, kp in zip(KEYPOINT_NAMES, person)
        ])


_estimator_cache: PoseEstimator | None = None


def get_estimator() -> PoseEstimator:
    global _estimator_cache
    if _estimator_cache is None:
        kind = os.environ.get("POSE_ESTIMATOR", "stub")
        if kind == "yolo":
            _estimator_cache = YoloPoseEstimator()
        else:
            _estimator_cache = StubPoseEstimator()
    return _estimator_cache

"""Model adapter boundary (D4). Swap the estimator without touching the API layer."""

import os
import random
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

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
    """Real adapter for a trained YOLO-pose model. Plug the model in by:
    1. `pip install ultralytics` (or your preferred YOLO-pose runtime)
    2. Load the trained weights in __init__, e.g.:
           from ultralytics import YOLO
           self.model = YOLO(os.environ["YOLO_POSE_WEIGHTS"])
    3. In estimate(): decode image_bytes (e.g. via PIL/cv2), run
           results = self.model(image)[0]
       and map `results.keypoints` (COCO-17, xy + conf) into the
       `[{name, x, y, confidence}, ...]` shape this class returns, using
       `pose_eval.KEYPOINT_NAMES` for the name order.
    """

    def __init__(self):
        # lazy import: don't require the ML runtime unless this estimator is selected
        try:
            import ultralytics  # noqa: F401
        except ImportError as exc:
            raise NotImplementedError(
                "YoloPoseEstimator requires a trained model; see class docstring "
                "for how to wire it up (ultralytics not installed)"
            ) from exc
        raise NotImplementedError("YoloPoseEstimator: plug in a trained model per the class docstring")

    def estimate(self, image_bytes: bytes) -> PoseResult:
        raise NotImplementedError


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

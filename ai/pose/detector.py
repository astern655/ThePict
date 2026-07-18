"""YOLO Pose 래퍼.

바깥에서는 '이미지 한 장 → 관절 17개'만 알면 되도록 ultralytics 세부사항을 감춘다.
YOLO를 다른 모델로 교체하려면 이 파일만 고치면 된다.
"""
from __future__ import annotations

import numpy as np

from ai.config import MODELS_DIR, POSE_MODEL
from ai.pose.keypoints import Keypoint

# 프레임에서 검출된 한 사람 = 관절 17개의 리스트.
Person = list[Keypoint]


class PoseDetector:
    def __init__(self, model_name: str = POSE_MODEL) -> None:
        # 무거운 import는 실제 사용 시점까지 미룬다(앱 기동 속도).
        from ultralytics import YOLO

        weights_path = MODELS_DIR / model_name
        # models/ 에 있으면 그걸, 없으면 이름만 넘겨 자동 다운로드하게 한다.
        target = str(weights_path) if weights_path.exists() else model_name
        self.model = YOLO(target)
        # 직전 프레임에서 고른 사람의 무게중심. 다인 환경에서 대상이
        # 프레임마다 다른 사람으로 튀지 않도록 '같은 사람'을 계속 따라간다.
        self._last_center: np.ndarray | None = None

    def reset(self) -> None:
        """새 영상 시작 시 호출. 직전 영상의 추적 대상을 잊는다."""
        self._last_center = None

    def detect(self, frame: np.ndarray) -> Person | None:
        """이미지 한 장에서 분석 대상 1명의 관절을 반환. 사람이 없으면 None.

        첫 프레임(또는 reset 직후)은 관절 신뢰도 합이 가장 큰 사람을 고르고,
        이후에는 직전에 골랐던 사람과 가장 가까운 검출을 따라간다.
        (배경에 다른 사람이 지나가도 대상이 바뀌지 않게)
        """
        results = self.model.predict(frame, verbose=False)
        if not results:
            return None

        result = results[0]
        kpts = result.keypoints
        if kpts is None or kpts.data is None or len(kpts.data) == 0:
            return None

        # data: (사람 수, 17, 3) = (x, y, confidence)
        data = kpts.data.cpu().numpy()

        conf = data[:, :, 2]                       # (사람 수, 17)
        conf_sums = conf.sum(axis=1)               # 사람별 신뢰도 합
        # 사람별 무게중심(신뢰도 가중 평균 좌표)
        weights = conf[:, :, None]
        centers = (data[:, :, :2] * weights).sum(axis=1) / np.maximum(
            weights.sum(axis=1), 1e-6
        )

        if self._last_center is not None and len(data) > 1:
            distances = np.linalg.norm(centers - self._last_center, axis=1)
            best_idx = int(np.argmin(distances))
        else:
            best_idx = int(np.argmax(conf_sums))

        self._last_center = centers[best_idx]
        person = data[best_idx]

        return [Keypoint(x=float(x), y=float(y), confidence=float(c)) for x, y, c in person]

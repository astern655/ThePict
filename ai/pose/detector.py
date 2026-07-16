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

    def detect(self, frame: np.ndarray) -> Person | None:
        """이미지 한 장에서 신뢰도가 가장 높은 사람 1명의 관절을 반환.

        사람이 없으면 None.
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

        # 여러 명이면 관절 신뢰도 합이 가장 큰 사람을 대표로 고른다.
        best_idx = int(np.argmax(data[:, :, 2].sum(axis=1)))
        person = data[best_idx]

        return [Keypoint(x=float(x), y=float(y), confidence=float(c)) for x, y, c in person]

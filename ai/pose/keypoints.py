"""COCO 17 관절 표준 정의.

YOLO Pose는 관절을 '인덱스'(0~16)로 돌려준다. 코드에서 [13] 대신
KP.LEFT_KNEE 처럼 이름으로 쓰기 위해 여기에 상수로 모아둔다.
"""
from __future__ import annotations

from dataclasses import dataclass


class KP:
    """COCO keypoint 인덱스."""
    NOSE = 0
    LEFT_EYE = 1
    RIGHT_EYE = 2
    LEFT_EAR = 3
    RIGHT_EAR = 4
    LEFT_SHOULDER = 5
    RIGHT_SHOULDER = 6
    LEFT_ELBOW = 7
    RIGHT_ELBOW = 8
    LEFT_WRIST = 9
    RIGHT_WRIST = 10
    LEFT_HIP = 11
    RIGHT_HIP = 12
    LEFT_KNEE = 13
    RIGHT_KNEE = 14
    LEFT_ANKLE = 15
    RIGHT_ANKLE = 16


# 관절을 선으로 이어 '뼈대(skeleton)'를 그릴 때 쓰는 연결 쌍.
SKELETON: list[tuple[int, int]] = [
    (KP.LEFT_SHOULDER, KP.RIGHT_SHOULDER),
    (KP.LEFT_SHOULDER, KP.LEFT_ELBOW), (KP.LEFT_ELBOW, KP.LEFT_WRIST),
    (KP.RIGHT_SHOULDER, KP.RIGHT_ELBOW), (KP.RIGHT_ELBOW, KP.RIGHT_WRIST),
    (KP.LEFT_SHOULDER, KP.LEFT_HIP), (KP.RIGHT_SHOULDER, KP.RIGHT_HIP),
    (KP.LEFT_HIP, KP.RIGHT_HIP),
    (KP.LEFT_HIP, KP.LEFT_KNEE), (KP.LEFT_KNEE, KP.LEFT_ANKLE),
    (KP.RIGHT_HIP, KP.RIGHT_KNEE), (KP.RIGHT_KNEE, KP.RIGHT_ANKLE),
]


@dataclass
class Keypoint:
    """관절 하나: 화면 좌표와 신뢰도."""
    x: float
    y: float
    confidence: float

    @property
    def visible(self) -> bool:
        from ai.config import MIN_KEYPOINT_CONFIDENCE
        return self.confidence >= MIN_KEYPOINT_CONFIDENCE

    def as_xy(self) -> tuple[float, float]:
        return (self.x, self.y)

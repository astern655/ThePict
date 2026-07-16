"""자세 측정용 순수 수학 함수 모음.

여기 있는 함수는 관절 좌표(숫자)만 받고 숫자만 돌려준다.
YOLO도, 운동 규칙도 몰라서 테스트하기 쉽다.
"""
from __future__ import annotations

import math

Point = tuple[float, float]


def angle_at(a: Point, b: Point, c: Point) -> float:
    """세 점 A-B-C 에서 가운데 점 B의 각도를 도(degree)로 반환.

    무릎각이면 A=엉덩이, B=무릎, C=발목.
    벡터 BA, BC 사이각을 코사인으로 구한다.
    """
    bax, bay = a[0] - b[0], a[1] - b[1]
    bcx, bcy = c[0] - b[0], c[1] - b[1]

    dot = bax * bcx + bay * bcy
    mag_ba = math.hypot(bax, bay)
    mag_bc = math.hypot(bcx, bcy)
    if mag_ba == 0 or mag_bc == 0:
        return float("nan")

    cos_theta = dot / (mag_ba * mag_bc)
    # 부동소수 오차로 [-1, 1] 범위를 벗어나면 arccos가 터지므로 잘라준다.
    cos_theta = max(-1.0, min(1.0, cos_theta))
    return math.degrees(math.acos(cos_theta))


def torso_incline(shoulder: Point, hip: Point) -> float:
    """상체가 수직선에서 얼마나 기울었는지(도). 0=완전 수직, 클수록 앞으로 숙임."""
    dx = shoulder[0] - hip[0]
    dy = shoulder[1] - hip[1]
    # 화면 y축은 아래로 갈수록 커진다. 수직 기준각을 잡는다.
    return abs(math.degrees(math.atan2(dx, -dy)))



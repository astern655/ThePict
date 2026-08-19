"""관절 스냅샷(Person) 단위 측정 헬퍼.

`geometry.py`는 점 세 개 같은 '숫자'만 다루고, 여기는 그 위층 —
"보이는 쪽만 골라서 재고, 좌우가 다 보이면 평균 낸다"는 규칙을 담는다.
운동 규칙(무엇이 결함인가)은 모르므로 `exercises/`가 이 함수들을 조합해 쓴다.

측면 촬영에서는 보통 한쪽 팔·다리만 잡히므로, 모든 함수가
**보이는 쪽만 쓰고 둘 다 보이면 평균**을 낸다.
"""
from __future__ import annotations

import math

from ai.analysis.geometry import angle_at, torso_incline
from ai.pose.detector import Person
from ai.pose.keypoints import KP

# 좌우 몸통(어깨, 엉덩이) — 몸통 길이·기울기 계산에 쓴다.
TORSOS: dict[str, tuple[int, int]] = {
    "left": (KP.LEFT_SHOULDER, KP.LEFT_HIP),
    "right": (KP.RIGHT_SHOULDER, KP.RIGHT_HIP),
}


def visible_all(person: Person, indices: tuple[int, ...]) -> bool:
    """지정한 관절이 모두 신뢰도 기준을 넘는가."""
    return all(person[i].visible for i in indices)


def mean_joint_angle(person: Person, joints: dict[str, tuple[int, int, int]]) -> float | None:
    """(a, b, c) 묶음별 가운데 관절 각도의 평균. 잴 수 있는 게 없으면 None.

    무릎각(엉덩이-무릎-발목), 팔꿈치각(어깨-팔꿈치-손목)처럼 쓴다.

    좌표가 완전히 겹치면 `angle_at`이 NaN을 낸다. NaN은 모든 비교가 False라
    상태기계를 조용히 멈추게 하므로, 여기서 **'못 잰 것'과 똑같이 걸러낸다.**
    """
    angles = [
        angle
        for (a, b, c) in joints.values()
        if visible_all(person, (a, b, c))
        if math.isfinite(
            angle := angle_at(person[a].as_xy(), person[b].as_xy(), person[c].as_xy())
        )
    ]
    if not angles:
        return None
    return sum(angles) / len(angles)


def mean_segment_incline(person: Person, segments: dict[str, tuple[int, int]]) -> float | None:
    """선분(위쪽 점, 아래쪽 점)이 수직에서 기운 각도의 평균. 안 보이면 None.

    상체 기울기(어깨-엉덩이), 정강이 기울기(무릎-발목)에 같은 계산을 쓴다.
    """
    values = [
        value
        for (top, bottom) in segments.values()
        if visible_all(person, (top, bottom))
        if math.isfinite(
            value := torso_incline(person[top].as_xy(), person[bottom].as_xy())
        )
    ]
    if not values:
        return None
    return sum(values) / len(values)


def mean_femur_elevation(person: Person,
                         femurs: dict[str, tuple[int, int]]) -> float | None:
    """대퇴(엉덩이-무릎)가 화면상 수평보다 몇 도 위에 있는가의 평균. 못 재면 None.

    스쿼트 깊이의 직접 지표다. 서 있으면 +90°, 허벅지가 수평이면 0°,
    엉덩이가 무릎보다 낮으면 음수. 무릎각과 달리 대퇴/정강이 길이 비율이나
    발목 유연성 같은 체형 차이에 흔들리지 않는다(LLM-FMS 검증:
    docs/LLM_FMS_VALIDATION.md — 무릎각 잔차 분산의 63%가 피험자 간 차이).

    화면 y축은 아래가 양수이므로 (무릎y − 엉덩이y)/대퇴 길이 = sin(거상각).
    """
    values = []
    for hip, knee in femurs.values():
        if not visible_all(person, (hip, knee)):
            continue
        h, k = person[hip], person[knee]
        length = math.hypot(h.x - k.x, h.y - k.y)
        if length <= 0:
            continue
        ratio = max(-1.0, min(1.0, (k.y - h.y) / length))
        values.append(math.degrees(math.asin(ratio)))
    if not values:
        return None
    return sum(values) / len(values)


def mean_hip_in_shin_span(person: Person,
                          legs: dict[str, tuple[int, int, int]]) -> float | None:
    """엉덩이가 '무릎~발목' 수직 구간의 어디에 있는가. 못 재면 None.

    0 = 무릎 높이, 양수 = 무릎보다 위(얕음), 음수 = 무릎보다 아래(깊음).
    [[mean_femur_elevation]]과 같은 것을 재지만 **정규화 기준이 다르다** —
    대퇴의 투영 길이 대신 정강이의 수직 성분을 쓴다. 대퇴 투영 길이는 몸이
    카메라 쪽으로 조금만 돌아도 짧아져 비율을 부풀리는데, 이 기준은 덜 흔들린다.

    아직 판정에는 쓰지 않고 측정값만 남긴다(채택 근거는 docs/LLM_FMS_VALIDATION.md).
    정강이가 화면상 수평에 가까우면 분모가 0에 붙어 불안정하므로 그 다리는 버린다.
    """
    values = []
    for hip, knee, ankle in legs.values():
        if not visible_all(person, (hip, knee, ankle)):
            continue
        h, k, a = person[hip], person[knee], person[ankle]
        span = a.y - k.y          # 화면 y는 아래가 양수 → 발목이 무릎보다 아래면 양수
        leg = math.hypot(k.x - a.x, k.y - a.y)
        # 정강이 길이 대비 수직 성분이 20% 미만이면(≈78° 이상 누움) 분모를 못 믿는다.
        if leg <= 0 or abs(span) < 0.2 * leg:
            continue
        values.append(-(h.y - k.y) / span)
    if not values:
        return None
    return sum(values) / len(values)


def torso_length(person: Person) -> float | None:
    """어깨-엉덩이 거리(픽셀)의 평균. 화면 크기·거리를 정규화하는 기준자."""
    lengths = [
        math.hypot(person[sh].x - person[hip].x, person[sh].y - person[hip].y)
        for sh, hip in TORSOS.values()
        if visible_all(person, (sh, hip))
    ]
    if not lengths:
        return None
    mean = sum(lengths) / len(lengths)
    return mean if mean > 0 else None


def side_view_ratio(person: Person) -> float | None:
    """좌우 어깨의 화면상 수평 간격 ÷ 몸통 길이.

    측면이면 어깨가 겹쳐 작고, 정면이면 어깨너비만큼 벌어져 크다.
    양 어깨와 몸통 한 쌍 이상이 보일 때만 계산 가능(아니면 None).

    스쿼트(선 자세)든 푸시업(엎드린 자세)든 몸통 길이는 방향과 무관한 거리라
    같은 지표가 성립한다. 다만 경계값은 스쿼트 영상으로만 확인했다
    (docs/SQUAT_TUNING.md §4).
    """
    ls, rs = person[KP.LEFT_SHOULDER], person[KP.RIGHT_SHOULDER]
    if not (ls.visible and rs.visible):
        return None
    length = torso_length(person)
    if length is None:
        return None
    return abs(ls.x - rs.x) / length


def hip_gap_ratio(person: Person) -> float | None:
    """좌우 엉덩이의 화면상 수평 간격 ÷ 몸통 길이.

    [[side_view_ratio]]와 같은 원리를 골반에 적용한 보조 지표. 정면에서는
    어깨가 팔 동작·가림으로 흔들려도 골반 간격은 안정적으로 벌어져 보인다.
    실측(푸시업 27편): 측면 바닥 자세 최대 0.659, 명백한 정면 1.63·3.74
    (docs/PUSHUP_TUNING.md §7-B 재설계).
    """
    lh, rh = person[KP.LEFT_HIP], person[KP.RIGHT_HIP]
    if not (lh.visible and rh.visible):
        return None
    length = torso_length(person)
    if length is None:
        return None
    return abs(lh.x - rh.x) / length


def torso_horizontality(person: Person) -> float | None:
    """몸통(어깨→엉덩이) 선분의 화면상 수평 성분 비율(0~1). 못 재면 None.

    엎드린 자세를 옆에서 찍으면 몸통이 화면을 가로질러 1에 붙고,
    머리쪽 정면·벽/인클라인 같은 선 자세 변형은 수직 성분이 커져 낮아진다.

    **네 관절(양 어깨·양 엉덩이)이 다 보이는 프레임에서 중점끼리만** 잰다 —
    경계(0.75)를 도출한 실측이 전부 이 정의다(§7-B: 엎드린 측면 0.849~0.998,
    정면·선 자세 0.074~0.689). 한쪽만 보이는 프레임의 개별 선분은 분포가
    달라(근접 원근에서 1.0 근처로 치솟음) 섞으면 중앙값이 오염된다 —
    RTExR kaggle_25 실측: 중점만 0.705(반려) vs 혼합 0.887(통과 누락).
    표본이 안 모이면 게이트 ③이 보류되는 것은 다른 지표와 같은 규칙이다.
    """
    ls, rs = person[KP.LEFT_SHOULDER], person[KP.RIGHT_SHOULDER]
    lh, rh = person[KP.LEFT_HIP], person[KP.RIGHT_HIP]
    if not (ls.visible and rs.visible and lh.visible and rh.visible):
        return None
    sx, sy = (ls.x + rs.x) / 2, (ls.y + rs.y) / 2
    hx, hy = (lh.x + rh.x) / 2, (lh.y + rh.y) / 2
    length = math.hypot(sx - hx, sy - hy)
    if length <= 0:
        return None
    return abs(sx - hx) / length


def is_below_line(start: tuple[float, float], end: tuple[float, float],
                  point: tuple[float, float]) -> bool | None:
    """point가 start–end 직선보다 화면상 아래(y가 큰 쪽)에 있는가.

    푸시업에서 엉덩이가 처졌는지(아래) 솟았는지(위)를 가른다. 몸이 어느 방향을
    보고 있든 결과가 같도록 외적 부호가 아니라 **같은 x에서의 y 비교**를 쓴다.
    선분이 화면상 거의 수직이면(엎드린 자세가 아니면) 비교가 무의미하므로 None.
    """
    vx = end[0] - start[0]
    if abs(vx) < 1e-6:
        return None
    t = (point[0] - start[0]) / vx
    expected_y = start[1] + t * (end[1] - start[1])
    return point[1] > expected_y

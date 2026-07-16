"""스쿼트 분석기 (측면 촬영 전용).

핵심: 무릎각을 프레임마다 재서
  (1) UP/DOWN 상태기계로 반복을 세고,
  (2) 한 번 앉았다 일어설 때의 '가장 깊이 앉은 프레임'을 기준으로 자세를 판정한다.

자세 판정은 반드시 **최저점(가장 깊이 앉은 순간)** 의 관절로 해야 의미가 있다.
서 있는 순간을 재면 상체 숙임이 거의 항상 정상으로 보이기 때문이다.

**측면 촬영을 전제로 한다.** 측면에서는 무릎 굽힘 깊이와 상체 앞숙임(앞뒤 기울기)을
정확히 볼 수 있다. 좌우 무릎 모임·비대칭은 좌우 관절이 화면상 겹쳐 측정할 수 없으므로
측면 분석에서는 다루지 않는다. (자세한 근거·촬영 가이드: docs/CAPTURE_AND_SQUAT_CRITERIA.md)
"""
from __future__ import annotations

from ai.analysis.exercises.base import ExerciseAnalyzer
from ai.analysis.feedback import Issue, Severity
from ai.analysis.geometry import angle_at, torso_incline
from ai.config import (
    SQUAT_GOOD_DEPTH_ANGLE,
    SQUAT_KNEE_DOWN_ANGLE,
    SQUAT_KNEE_UP_ANGLE,
    SQUAT_TORSO_LEAN_MAX,
)
from ai.pose.detector import Person
from ai.pose.keypoints import KP

# 한쪽 다리 = (엉덩이, 무릎, 발목) 관절 인덱스 묶음
_LEGS = {
    "left": (KP.LEFT_HIP, KP.LEFT_KNEE, KP.LEFT_ANKLE),
    "right": (KP.RIGHT_HIP, KP.RIGHT_KNEE, KP.RIGHT_ANKLE),
}
_TORSOS = {
    "left": (KP.LEFT_SHOULDER, KP.LEFT_HIP),
    "right": (KP.RIGHT_SHOULDER, KP.RIGHT_HIP),
}


def _leg_visible(person: Person, leg: tuple[int, int, int]) -> bool:
    return all(person[i].visible for i in leg)


def _knee_angle(person: Person, leg: tuple[int, int, int]) -> float:
    hip, knee, ankle = leg
    return angle_at(person[hip].as_xy(), person[knee].as_xy(), person[ankle].as_xy())


def _side_knee_angles(person: Person) -> dict[str, float]:
    """보이는 쪽 다리의 무릎각만 {side: angle}로 반환."""
    return {
        side: _knee_angle(person, leg)
        for side, leg in _LEGS.items()
        if _leg_visible(person, leg)
    }


def _mid_knee_angle(person: Person) -> float | None:
    """양 무릎각의 평균. 한쪽만 보이면 보이는 쪽만 사용.

    측면에서는 보통 한쪽 다리만 보이지만, 두 다리가 모두 잡히면 평균으로 안정화한다.
    """
    angles = list(_side_knee_angles(person).values())
    if not angles:
        return None
    return sum(angles) / len(angles)


def _torso_lean(person: Person) -> float | None:
    """몸통 기울기(도). 보이는 쪽(좌/우)을 쓰고, 둘 다 보이면 평균."""
    vals = [
        torso_incline(person[sh].as_xy(), person[hip].as_xy())
        for sh, hip in _TORSOS.values()
        if person[sh].visible and person[hip].visible
    ]
    if not vals:
        return None
    return sum(vals) / len(vals)


# --- rep 최저점(bottom) 스냅샷 기준 순수 규칙 검사 -----------------------
# 각 함수는 관절 스냅샷을 받아 결함이면 Issue, 아니면 None을 돌려준다.
# (깊이만은 최저 무릎각 숫자를 직접 받는다.) 순수 함수로 두면 단위 테스트가 쉽다.

def check_depth(min_knee_angle: float, rep: int) -> Issue:
    """최저점 무릎각으로 깊이를 판정. 항상 하나(좋음/부족)를 반환."""
    if min_knee_angle > SQUAT_GOOD_DEPTH_ANGLE:
        return Issue(
            rep_index=rep, code="shallow_depth", severity=Severity.WARNING,
            message="더 깊게 앉으세요 (허벅지가 바닥과 수평이 되도록).",
            measured=round(min_knee_angle, 1),
        )
    return Issue(
        rep_index=rep, code="good_depth", severity=Severity.GOOD,
        message="충분한 깊이로 잘 앉았습니다.",
        measured=round(min_knee_angle, 1),
    )


def check_torso(person: Person, rep: int) -> Issue | None:
    """상체 과도한 앞숙임. 좌우 중 보이는 쪽으로 측정. (측면에서 유효)"""
    incline = _torso_lean(person)
    if incline is None:
        return None
    if incline > SQUAT_TORSO_LEAN_MAX:
        return Issue(
            rep_index=rep, code="torso_lean", severity=Severity.WARNING,
            message="상체가 과하게 앞으로 숙여졌습니다. 가슴을 펴세요.",
            measured=round(incline, 1),
        )
    return None


class SquatAnalyzer(ExerciseAnalyzer):
    name = "스쿼트"

    def __init__(self) -> None:
        super().__init__()
        self.state = "UP"              # 시작은 서 있다고 가정
        self.min_knee_in_rep = 180.0   # 현재 rep에서 관측된 최저 무릎각
        self._bottom_person: Person | None = None  # 최저각 프레임의 관절 스냅샷

    def update(self, person: Person | None, frame_index: int) -> None:
        if person is None:
            return
        knee_angle = _mid_knee_angle(person)
        if knee_angle is None:
            return

        # 내려가는 동안 최저각을 추적하고, 그 순간의 관절을 통째로 붙든다.
        # 자세 판정은 이 '가장 깊이 앉은 프레임'으로 해야 의미가 있다.
        if self.state == "DOWN" or knee_angle < SQUAT_KNEE_UP_ANGLE:
            if knee_angle < self.min_knee_in_rep:
                self.min_knee_in_rep = knee_angle
                self._bottom_person = person

        # --- 상태기계 ---
        if self.state == "UP" and knee_angle < SQUAT_KNEE_DOWN_ANGLE:
            self.state = "DOWN"
        elif self.state == "DOWN" and knee_angle > SQUAT_KNEE_UP_ANGLE:
            # DOWN → UP 전환 = 반복 1회 완료
            self.state = "UP"
            self.report.rep_count += 1
            self._check_form(self.report.rep_count)
            # 다음 rep을 위해 초기화
            self.min_knee_in_rep = 180.0
            self._bottom_person = None

    def _check_form(self, rep: int) -> None:
        """방금 끝난 rep의 최저점 자세를 측면 규칙(깊이·상체 앞숙임)으로 검사해 리포트에 추가."""
        # 규칙 1: 깊이 (항상 판정)
        self.report.add(check_depth(self.min_knee_in_rep, rep))

        # 규칙 2: 상체 앞숙임 (최저점 스냅샷 기준)
        if self._bottom_person is not None:
            issue = check_torso(self._bottom_person, rep)
            if issue is not None:
                self.report.add(issue)

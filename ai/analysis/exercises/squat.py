"""스쿼트 분석기.

핵심: 무릎각을 프레임마다 재서 (1) UP/DOWN 상태기계로 반복을 세고,
(2) 한 번 앉았다 일어설 때의 '최저 무릎각' 등으로 자세를 판정한다.
"""
from __future__ import annotations

from ai.analysis.exercises.base import ExerciseAnalyzer
from ai.analysis.feedback import Issue, Severity
from ai.analysis.geometry import angle_at, horizontal_gap, torso_incline
from ai.config import (
    SQUAT_GOOD_DEPTH_ANGLE,
    SQUAT_KNEE_DOWN_ANGLE,
    SQUAT_KNEE_UP_ANGLE,
)
from ai.pose.detector import Person
from ai.pose.keypoints import KP


def _mid_knee_angle(person: Person) -> float | None:
    """양 무릎각의 평균. 한쪽만 보이면 보이는 쪽만 사용."""
    angles = []
    for hip, knee, ankle in (
        (KP.LEFT_HIP, KP.LEFT_KNEE, KP.LEFT_ANKLE),
        (KP.RIGHT_HIP, KP.RIGHT_KNEE, KP.RIGHT_ANKLE),
    ):
        if person[hip].visible and person[knee].visible and person[ankle].visible:
            angles.append(
                angle_at(person[hip].as_xy(), person[knee].as_xy(), person[ankle].as_xy())
            )
    if not angles:
        return None
    return sum(angles) / len(angles)


class SquatAnalyzer(ExerciseAnalyzer):
    name = "스쿼트"

    def __init__(self) -> None:
        super().__init__()
        self.state = "UP"             # 시작은 서 있다고 가정
        self.min_knee_in_rep = 180.0  # 현재 rep에서 관측된 최저 무릎각

    def update(self, person: Person | None, frame_index: int) -> None:
        if person is None:
            return
        knee_angle = _mid_knee_angle(person)
        if knee_angle is None:
            return

        # 내려가는 동안 최저각을 계속 추적
        if self.state == "DOWN" or knee_angle < SQUAT_KNEE_UP_ANGLE:
            self.min_knee_in_rep = min(self.min_knee_in_rep, knee_angle)

        # --- 상태기계 ---
        if self.state == "UP" and knee_angle < SQUAT_KNEE_DOWN_ANGLE:
            self.state = "DOWN"
        elif self.state == "DOWN" and knee_angle > SQUAT_KNEE_UP_ANGLE:
            # DOWN → UP 전환 = 반복 1회 완료
            self.state = "UP"
            self.report.rep_count += 1
            self._check_form(person, self.report.rep_count)
            self.min_knee_in_rep = 180.0  # 다음 rep 위해 초기화

    def _check_form(self, person: Person, rep: int) -> None:
        """방금 끝난 rep의 자세 결함을 검사해 리포트에 추가."""
        # 규칙 1: 깊이
        if self.min_knee_in_rep > SQUAT_GOOD_DEPTH_ANGLE:
            self.report.add(Issue(
                rep_index=rep, code="shallow_depth", severity=Severity.WARNING,
                message="더 깊게 앉으세요 (허벅지가 바닥과 수평이 되도록).",
                measured=round(self.min_knee_in_rep, 1),
            ))
        else:
            self.report.add(Issue(
                rep_index=rep, code="good_depth", severity=Severity.GOOD,
                message="충분한 깊이로 잘 앉았습니다.",
                measured=round(self.min_knee_in_rep, 1),
            ))

        # 규칙 2: 무릎 모임 (무릎 간격이 발목 간격보다 좁으면 안쪽으로 무너진 것)
        if all(person[i].visible for i in (KP.LEFT_KNEE, KP.RIGHT_KNEE, KP.LEFT_ANKLE, KP.RIGHT_ANKLE)):
            knee_gap = horizontal_gap(person[KP.LEFT_KNEE].as_xy(), person[KP.RIGHT_KNEE].as_xy())
            ankle_gap = horizontal_gap(person[KP.LEFT_ANKLE].as_xy(), person[KP.RIGHT_ANKLE].as_xy())
            if ankle_gap > 0 and knee_gap < ankle_gap * 0.8:
                self.report.add(Issue(
                    rep_index=rep, code="knee_valgus", severity=Severity.ERROR,
                    message="무릎이 안쪽으로 모입니다. 무릎을 발끝 방향으로 벌리세요.",
                    measured=round(knee_gap / ankle_gap, 2),
                ))

        # 규칙 3: 상체 과도한 앞숙임 (측면 촬영에서 유효)
        if person[KP.LEFT_SHOULDER].visible and person[KP.LEFT_HIP].visible:
            incline = torso_incline(person[KP.LEFT_SHOULDER].as_xy(), person[KP.LEFT_HIP].as_xy())
            if incline > 45.0:
                self.report.add(Issue(
                    rep_index=rep, code="torso_lean", severity=Severity.WARNING,
                    message="상체가 과하게 앞으로 숙여졌습니다. 가슴을 펴세요.",
                    measured=round(incline, 1),
                ))

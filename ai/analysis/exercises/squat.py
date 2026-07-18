"""스쿼트 분석기 (측면 촬영 전용).

핵심: 무릎각을 프레임마다 재서(중앙값 필터로 평활화)
  (1) UP/DOWN 상태기계로 반복을 세고,
  (2) 한 번 앉았다 일어설 때의 '가장 깊이 앉은 프레임'을 기준으로 자세를 판정한다.

자세 판정은 반드시 **최저점(가장 깊이 앉은 순간)** 의 관절로 해야 의미가 있다.
서 있는 순간을 재면 상체 숙임이 거의 항상 정상으로 보이기 때문이다.

**측면 촬영을 전제로 한다.** 평가하는 규칙은 측면 2D 좌표만으로 확실히 잴 수 있는
깊이(무릎각)와 상체 앞숙임 두 가지뿐이다. 좌우 무릎 모임·비대칭은 좌우 관절이 화면상
겹쳐 측정할 수 없어 다루지 않는다. 대신 영상이 실제로 측면인지(어깨 간격/몸통 길이
비율)를 자동 검증해, 정면 영상이 들어오면 리포트에 경고를 남긴다.
(자세한 근거·촬영 가이드: docs/CAPTURE_AND_SQUAT_CRITERIA.md)
"""
from __future__ import annotations

import math
import statistics

from ai.analysis.exercises.base import ExerciseAnalyzer
from ai.analysis.feedback import Issue, RepRecord, Severity
from ai.analysis.filters import MedianSmoother
from ai.analysis.geometry import angle_at, torso_incline
from ai.config import (
    SIDE_VIEW_MIN_SAMPLES,
    SIDE_VIEW_RATIO_MAX,
    SQUAT_ANGLE_SMOOTH_WINDOW,
    SQUAT_GOOD_DEPTH_ANGLE,
    SQUAT_KNEE_DOWN_ANGLE,
    SQUAT_KNEE_UP_ANGLE,
    SQUAT_PARTIAL_DIP_ANGLE,
    SQUAT_SEVERE_DEPTH_ANGLE,
    SQUAT_TORSO_LEAN_HARD_MAX,
    SQUAT_TORSO_SHIN_DIFF_SEVERE,
    SQUAT_TORSO_SHIN_DIFF_WARN,
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


def _shin_incline(person: Person) -> float | None:
    """정강이 기울기(도, 수직 기준). 보이는 다리를 쓰고, 둘 다 보이면 평균.

    torso_incline과 같은 계산을 (무릎, 발목)에 적용한 것.
    상체 앞숙임 판정의 기준선(정상 균형에서 상체는 정강이를 따라 기운다)이 된다.
    """
    vals = [
        torso_incline(person[knee].as_xy(), person[ankle].as_xy())
        for _hip, knee, ankle in _LEGS.values()
        if person[knee].visible and person[ankle].visible
    ]
    if not vals:
        return None
    return sum(vals) / len(vals)


def _view_ratio(person: Person) -> float | None:
    """좌우 어깨의 화면상 수평 간격 ÷ 몸통 길이.

    측면이면 어깨가 겹쳐 작고, 정면이면 어깨너비만큼 벌어져 크다.
    양 어깨와 몸통(어깨-엉덩이) 한 쌍 이상이 보일 때만 계산 가능.
    """
    ls, rs = person[KP.LEFT_SHOULDER], person[KP.RIGHT_SHOULDER]
    if not (ls.visible and rs.visible):
        return None
    torso_lengths = [
        math.hypot(person[sh].x - person[hip].x, person[sh].y - person[hip].y)
        for sh, hip in _TORSOS.values()
        if person[sh].visible and person[hip].visible
    ]
    if not torso_lengths:
        return None
    torso_len = sum(torso_lengths) / len(torso_lengths)
    if torso_len <= 0:
        return None
    return abs(ls.x - rs.x) / torso_len


# --- rep 최저점(bottom) 스냅샷 기준 순수 규칙 검사 -----------------------
# 각 함수는 관절 스냅샷을 받아 결함이면 Issue, 아니면 None을 돌려준다.
# (깊이만은 최저 무릎각 숫자를 직접 받는다.) 순수 함수로 두면 단위 테스트가 쉽다.

def check_depth(min_knee_angle: float, rep: int) -> Issue:
    """최저점 무릎각으로 깊이를 판정. 항상 하나(좋음/부족/거의 안 앉음)를 반환.

    각이 클수록 덜 앉은 것이다. 심각 임계(120°)를 넘으면 스쿼트라 보기 어려운
    수준이라 ERROR로 올려 rep 판정을 '잘못됨'으로 만든다.
    """
    measured = round(min_knee_angle, 1)
    if min_knee_angle > SQUAT_SEVERE_DEPTH_ANGLE:
        return Issue(
            rep_index=rep, code="very_shallow_depth", severity=Severity.ERROR,
            message="거의 앉지 않았습니다. 무릎을 훨씬 더 굽혀 엉덩이를 무릎 높이까지 내리세요.",
            measured=measured,
        )
    if min_knee_angle > SQUAT_GOOD_DEPTH_ANGLE:
        return Issue(
            rep_index=rep, code="shallow_depth", severity=Severity.WARNING,
            message="깊이가 조금 모자랍니다. 허벅지가 바닥과 수평이 될 때까지 더 앉으세요.",
            measured=measured,
        )
    return Issue(
        rep_index=rep, code="good_depth", severity=Severity.GOOD,
        message="충분한 깊이로 잘 앉았습니다.",
        measured=measured,
    )


def check_torso(person: Person, rep: int) -> Issue | None:
    """상체 앞숙임. 정강이 기울기와의 차이로 판정한다. (측면에서만 유효)

    깊게 앉을수록 무릎이 앞으로 나가며 정강이가 기울고, 상체도 그만큼 따라
    기우는 것이 정상 균형이다. 그래서 절대각이 아니라 '상체가 정강이보다
    얼마나 더 접혔는가'(상체−정강이)로 재야 깊은 스쿼트를 처벌하지 않는다.
    단, 상체가 수평에 가까우면(절대 기울기 > 70°) 정강이와 무관하게 결함이다.
    """
    incline = _torso_lean(person)
    if incline is None:
        return None
    if incline > SQUAT_TORSO_LEAN_HARD_MAX:
        return Issue(
            rep_index=rep, code="excessive_torso_lean", severity=Severity.ERROR,
            message="상체가 거의 수평까지 숙여졌습니다. 허리 부상 위험이 크니 "
                    "가슴을 세우고 다시 앉으세요.",
            measured=round(incline, 1),
        )
    shin = _shin_incline(person)
    if shin is None:
        return None  # 다리가 안 보이면 상대 판정은 보류(절대 상한만 위에서 검사)
    diff = round(incline - shin, 1)
    if diff > SQUAT_TORSO_SHIN_DIFF_SEVERE:
        return Issue(
            rep_index=rep, code="excessive_torso_lean", severity=Severity.ERROR,
            message="엉덩이만 뒤로 빠지고 상체가 접히는 굿모닝 자세입니다. "
                    "허리 부담이 크니 가슴을 세우고 무릎을 함께 굽히세요.",
            measured=diff,
        )
    if diff > SQUAT_TORSO_SHIN_DIFF_WARN:
        return Issue(
            rep_index=rep, code="torso_lean", severity=Severity.WARNING,
            message="상체가 정강이보다 과하게 앞으로 접혔습니다. "
                    "엉덩이를 덜 빼고 가슴을 세우며 앉으세요.",
            measured=diff,
        )
    return None


class SquatAnalyzer(ExerciseAnalyzer):
    name = "스쿼트"

    def __init__(self, fps: float | None = None) -> None:
        super().__init__(fps)
        self.state = "UP"              # 시작은 서 있다고 가정
        self.min_knee_in_rep = 180.0   # 현재 rep에서 관측된 최저 무릎각(평활값)
        self._bottom_person: Person | None = None  # 최저각 프레임의 관절 스냅샷
        self._bottom_frame = 0         # 최저각이 나온 프레임 번호
        self._smoother = MedianSmoother(SQUAT_ANGLE_SMOOTH_WINDOW)
        self._last_angle: float | None = None      # HUD 표시용 최근 평활 각
        # '내려감(dip)' 추적: UP 임계 아래로 내려간 구간. rep이 되면 시작점으로,
        # DOWN까지 못 가고 끝나면 부분 반복(partial rep)으로 쓴다.
        self._dip_start_frame: int | None = None
        self._dip_min = 180.0
        self._view_ratios: list[float] = []        # 측면 검증 표본

    def update(self, person: Person | None, frame_index: int) -> None:
        if person is None:
            return

        ratio = _view_ratio(person)
        if ratio is not None:
            self._view_ratios.append(ratio)

        raw_angle = _mid_knee_angle(person)
        if raw_angle is None:
            return
        knee_angle = self._smoother.push(raw_angle)
        self._last_angle = knee_angle

        # --- dip(내려감 구간) 추적: 시작·최저각 ---
        if knee_angle < SQUAT_KNEE_UP_ANGLE:
            if self._dip_start_frame is None:
                self._dip_start_frame = frame_index
            self._dip_min = min(self._dip_min, knee_angle)

        # 내려가는 동안 최저각을 추적하고, 그 순간의 관절을 통째로 붙든다.
        # 자세 판정은 이 '가장 깊이 앉은 프레임'으로 해야 의미가 있다.
        if self.state == "DOWN" or knee_angle < SQUAT_KNEE_UP_ANGLE:
            if knee_angle < self.min_knee_in_rep:
                self.min_knee_in_rep = knee_angle
                self._bottom_person = person
                self._bottom_frame = frame_index

        # --- 상태기계 ---
        if self.state == "UP":
            if knee_angle < SQUAT_KNEE_DOWN_ANGLE:
                self.state = "DOWN"
            elif knee_angle > SQUAT_KNEE_UP_ANGLE and self._dip_start_frame is not None:
                # DOWN까지 못 간 채 다시 일어섬 → 충분히 내려갔었다면 부분 반복
                if self._dip_min < SQUAT_PARTIAL_DIP_ANGLE:
                    self.report.partial_rep_count += 1
                self._reset_rep_tracking()
        elif self.state == "DOWN" and knee_angle > SQUAT_KNEE_UP_ANGLE:
            # DOWN → UP 전환 = 반복 1회 완료
            self.state = "UP"
            self.report.rep_count += 1
            self._finish_rep(self.report.rep_count, frame_index)
            self._reset_rep_tracking()

    def _reset_rep_tracking(self) -> None:
        self.min_knee_in_rep = 180.0
        self._bottom_person = None
        self._dip_start_frame = None
        self._dip_min = 180.0

    def _finish_rep(self, rep: int, end_frame: int) -> None:
        """방금 끝난 rep의 구간 정보를 기록하고 자세 규칙을 검사한다."""
        start_frame = self._dip_start_frame if self._dip_start_frame is not None else end_frame
        record = RepRecord(
            rep_index=rep,
            start_frame=start_frame,
            bottom_frame=self._bottom_frame,
            end_frame=end_frame,
            bottom_angle=round(self.min_knee_in_rep, 1),
            start_sec=self.seconds(start_frame),
            bottom_sec=self.seconds(self._bottom_frame),
            end_sec=self.seconds(end_frame),
        )
        if self.fps is not None:
            record.duration_sec = round((end_frame - start_frame) / self.fps, 2)
            record.descent_sec = round((self._bottom_frame - start_frame) / self.fps, 2)
            record.ascent_sec = round((end_frame - self._bottom_frame) / self.fps, 2)
        self.report.reps.append(record)
        self._check_form(rep)

    def _check_form(self, rep: int) -> None:
        """rep 최저점 자세를 측면 규칙(깊이·상체 앞숙임)으로 검사."""
        # 규칙 1: 깊이 (항상 판정)
        self.report.add(check_depth(self.min_knee_in_rep, rep))

        # 규칙 2: 최저점 스냅샷 기준 상체 앞숙임
        if self._bottom_person is not None:
            torso_issue = check_torso(self._bottom_person, rep)
            if torso_issue is not None:
                self.report.add(torso_issue)

    def finalize(self):
        # 측면 촬영 검증: 표본이 충분한데 어깨가 넓게 벌어져 보이면 정면 촬영이다.
        if len(self._view_ratios) >= SIDE_VIEW_MIN_SAMPLES:
            ratio = statistics.median(self._view_ratios)
            if ratio > SIDE_VIEW_RATIO_MAX:
                self.report.add_video_issue(Issue(
                    rep_index=0, code="not_side_view", severity=Severity.ERROR,
                    message="측면 촬영이 아닌 것으로 보입니다. 옆에서 다시 촬영해 주세요. "
                            "(정면 영상에서는 깊이·상체 판정이 부정확합니다)",
                    measured=round(ratio, 2),
                ))

        # 앉은 상태(DOWN)에서 영상이 끝나면 그 rep은 상태기계가 완료를 못 본다.
        # 조용히 버리지 않고, 횟수에서 빠졌음을 안내한다(깊이 부족과는 다른 사유).
        if self.state == "DOWN":
            self.report.add_video_issue(Issue(
                rep_index=0, code="ended_mid_rep", severity=Severity.WARNING,
                message="앉은 자세에서 영상이 끝나 마지막 동작 1회는 횟수에 포함되지 "
                        "않았습니다. 완전히 일어선 뒤 촬영을 종료해 주세요.",
                measured=round(self.min_knee_in_rep, 1),
            ))

        if self.report.partial_rep_count:
            self.report.add_video_issue(Issue(
                rep_index=0, code="partial_reps", severity=Severity.WARNING,
                message=f"충분히 앉지 못해 횟수에서 제외된 움직임이 "
                        f"{self.report.partial_rep_count}회 있습니다. 더 깊게 앉아 보세요.",
                measured=float(self.report.partial_rep_count),
            ))
        return self.report

    def hud_lines(self) -> list[str]:
        lines = [f"Reps: {self.report.rep_count}", f"State: {self.state}"]
        if self._last_angle is not None:
            lines.append(f"Knee: {self._last_angle:.0f} deg")
        return lines

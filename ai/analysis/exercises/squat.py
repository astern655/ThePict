"""스쿼트 분석기 (측면 촬영 전용).

핵심: 무릎각을 프레임마다 재서(중앙값 필터로 평활화)
  (1) UP/DOWN 상태기계로 반복을 세고,
  (2) 한 번 앉았다 일어설 때의 '가장 깊이 앉은 프레임'을 기준으로 자세를 판정한다.

(1)의 기계 부분은 `base.AngleRepAnalyzer`에 있다. 이 파일에는 **스쿼트에만
해당하는 것** — 어떤 관절각을 재는가, 무엇을 결함으로 보는가 — 만 남긴다.

자세 판정은 반드시 **최저점(가장 깊이 앉은 순간)** 의 관절로 해야 의미가 있다.
서 있는 순간을 재면 상체 숙임이 거의 항상 정상으로 보이기 때문이다.

**측면 촬영을 전제로 한다.** 평가하는 규칙은 측면 2D 좌표만으로 확실히 잴 수 있는
깊이(대퇴 거상각, 예비로 무릎각)와 상체 앞숙임 두 가지뿐이다. 좌우 무릎 모임·비대칭은 좌우 관절이 화면상
겹쳐 측정할 수 없어 다루지 않는다. 대신 영상이 실제로 측면인지(어깨 간격/몸통 길이
비율)를 자동 검증해, 정면 영상이 들어오면 리포트에 경고를 남긴다.
(자세한 근거·촬영 가이드: docs/CAPTURE_AND_SQUAT_CRITERIA.md)
"""
from __future__ import annotations

import statistics

from ai.analysis.exercises.base import AngleRepAnalyzer
from ai.analysis.feedback import Issue, RepRecord, Severity
from ai.analysis.landmarks import (
    mean_femur_elevation,
    mean_hip_in_shin_span,
    mean_joint_angle,
    mean_segment_incline,
)
from ai.config import (
    SQUAT_ANGLE_SMOOTH_WINDOW,
    SQUAT_FEMUR_BOTTOM_WINDOW,
    SQUAT_FEMUR_ELEVATION_SEVERE,
    SQUAT_FEMUR_ELEVATION_WARN,
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
# 정강이 = (무릎, 발목). 상체와 같은 계산(수직 기준 기울기)을 적용한다.
_SHINS = {
    "left": (KP.LEFT_KNEE, KP.LEFT_ANKLE),
    "right": (KP.RIGHT_KNEE, KP.RIGHT_ANKLE),
}
# 대퇴 = (엉덩이, 무릎). 깊이 판정 지표(대퇴 거상각)를 잰다.
_FEMURS = {
    "left": (KP.LEFT_HIP, KP.LEFT_KNEE),
    "right": (KP.RIGHT_HIP, KP.RIGHT_KNEE),
}


def _mid_knee_angle(person: Person) -> float | None:
    """양 무릎각의 평균. 한쪽만 보이면 보이는 쪽만 사용.

    측면에서는 보통 한쪽 다리만 보이지만, 두 다리가 모두 잡히면 평균으로 안정화한다.
    """
    return mean_joint_angle(person, _LEGS)


def _torso_lean(person: Person) -> float | None:
    """몸통 기울기(도). 보이는 쪽(좌/우)을 쓰고, 둘 다 보이면 평균."""
    return mean_segment_incline(person, _TORSOS)


def _shin_incline(person: Person) -> float | None:
    """정강이 기울기(도, 수직 기준). 보이는 다리를 쓰고, 둘 다 보이면 평균.

    상체 앞숙임 판정의 기준선(정상 균형에서 상체는 정강이를 따라 기운다)이 된다.
    """
    return mean_segment_incline(person, _SHINS)


# --- rep 최저점(bottom) 스냅샷 기준 순수 규칙 검사 -----------------------
# 각 함수는 관절 스냅샷을 받아 결함이면 Issue, 아니면 None을 돌려준다.
# (깊이만은 최저 무릎각 숫자를 직접 받는다.) 순수 함수로 두면 단위 테스트가 쉽다.

def check_depth_femur(femur_elevation: float, rep: int) -> Issue:
    """최저점 대퇴 거상각으로 깊이를 판정. 항상 하나를 반환. (1차 지표)

    거상각이 클수록 엉덩이가 무릎보다 높이 머문 것 = 덜 앉은 것이다.
    허벅지가 수평(0°)이면 표준 코칭 기준("허벅지가 바닥과 평행")을 만족한다.

    무릎각 대신 이 지표를 쓰는 이유: 같은 무릎각이라도 대퇴/정강이 길이
    비율·발목 유연성에 따라 실제 엉덩이 높이가 사람마다 달라(LLM-FMS 잔차
    분산의 63%가 피험자 간 차이), 무릎각으로는 재현율에 상한이 있었다.
    검증 근거와 임계값 선택 절차는 ai/config.py와 docs/LLM_FMS_VALIDATION.md.
    """
    measured = round(femur_elevation, 1)
    if measured > SQUAT_FEMUR_ELEVATION_SEVERE:
        return Issue(
            rep_index=rep, code="very_shallow_depth", severity=Severity.ERROR,
            message="거의 앉지 않았습니다. 이번 회차는 엉덩이를 무릎 높이까지 "
                    "확실히 내려 주세요.",
            measured=measured, threshold=SQUAT_FEMUR_ELEVATION_SEVERE,
        )
    if measured > SQUAT_FEMUR_ELEVATION_WARN:
        return Issue(
            rep_index=rep, code="shallow_depth", severity=Severity.WARNING,
            message="깊이가 조금 모자랍니다. 이번 회차는 허벅지가 바닥과 수평이 될 "
                    "때까지 더 앉으세요.",
            measured=measured, threshold=SQUAT_FEMUR_ELEVATION_WARN,
        )
    return Issue(
        rep_index=rep, code="good_depth", severity=Severity.GOOD,
        message="충분한 깊이로 잘 앉았습니다.",
        measured=measured, threshold=SQUAT_FEMUR_ELEVATION_WARN,
    )


def check_depth(min_knee_angle: float, rep: int) -> Issue:
    """최저점 무릎각으로 깊이를 판정하는 **예비** 기준. 항상 하나를 반환.

    최저점 스냅샷이 유실돼 대퇴 거상각을 못 잰 rep에서만 쓴다(check_form 참고).
    각이 클수록 덜 앉은 것이다. 설정된 심각 임계를 넘으면 ERROR로 올려
    rep 판정을 '잘못됨'으로 만든다.
    """
    # 표시값과 판정값을 항상 같게 두려고 반올림 뒤에 비교한다. 경계 부근 원시값이
    # 기준값으로 표시되면 판정도 그 표시값 기준으로 내려야 "측정값=기준값인데
    # ERROR"인 모순이 생기지 않는다. (경계는 초과일 때만 승급)
    measured = round(min_knee_angle, 1)
    if measured > SQUAT_SEVERE_DEPTH_ANGLE:
        return Issue(
            rep_index=rep, code="very_shallow_depth", severity=Severity.ERROR,
            message="거의 앉지 않았습니다. 이번 회차는 무릎을 훨씬 더 굽혀 "
                    "엉덩이를 무릎 높이까지 내리세요.",
            measured=measured, threshold=SQUAT_SEVERE_DEPTH_ANGLE,
        )
    if measured > SQUAT_GOOD_DEPTH_ANGLE:
        return Issue(
            rep_index=rep, code="shallow_depth", severity=Severity.WARNING,
            message="깊이가 조금 모자랍니다. 이번 회차는 허벅지가 바닥과 수평이 될 "
                    "때까지 더 앉으세요.",
            measured=measured, threshold=SQUAT_GOOD_DEPTH_ANGLE,
        )
    return Issue(
        rep_index=rep, code="good_depth", severity=Severity.GOOD,
        message="충분한 깊이로 잘 앉았습니다.",
        measured=measured, threshold=SQUAT_GOOD_DEPTH_ANGLE,
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
    # 아래 diff와 같은 이유로 반올림 뒤에 비교한다(표시값 = 판정값).
    if round(incline, 1) > SQUAT_TORSO_LEAN_HARD_MAX:
        return Issue(
            rep_index=rep, code="excessive_torso_lean", severity=Severity.ERROR,
            message="상체가 거의 수평까지 숙여졌습니다. 허리 부상 위험이 크니 "
                    "이번 회차는 가슴을 세우고 시선을 앞에 둔 채 다시 앉으세요.",
            measured=round(incline, 1), threshold=SQUAT_TORSO_LEAN_HARD_MAX,
        )
    shin = _shin_incline(person)
    if shin is None:
        return None  # 다리가 안 보이면 상대 판정은 보류(절대 상한만 위에서 검사)
    # 표시값과 판정값을 같게 두려고 반올림 뒤에 비교한다. 따라서 경계 바로 위의
    # 원시값도 표시상 경계값이면 경고가 아니다('초과'일 때만 승급).
    diff = round(incline - shin, 1)
    if diff > SQUAT_TORSO_SHIN_DIFF_SEVERE:
        return Issue(
            rep_index=rep, code="excessive_torso_lean", severity=Severity.ERROR,
            message="엉덩이만 뒤로 빠지고 상체가 접히는 굿모닝 자세입니다. 허리 부담이 "
                    "크니 이번 회차는 무릎을 먼저 굽혀 앉으면서 가슴을 세우세요.",
            measured=diff, threshold=SQUAT_TORSO_SHIN_DIFF_SEVERE,
        )
    if diff > SQUAT_TORSO_SHIN_DIFF_WARN:
        return Issue(
            rep_index=rep, code="torso_lean", severity=Severity.WARNING,
            message="상체가 정강이보다 과하게 앞으로 접혔습니다. 이번 회차는 엉덩이를 "
                    "덜 빼고 가슴을 세운 채 무릎을 굽혀 앉으세요.",
            measured=diff, threshold=SQUAT_TORSO_SHIN_DIFF_WARN,
        )
    return None


class SquatAnalyzer(AngleRepAnalyzer):
    name = "스쿼트"

    down_angle = SQUAT_KNEE_DOWN_ANGLE
    up_angle = SQUAT_KNEE_UP_ANGLE
    partial_dip_angle = SQUAT_PARTIAL_DIP_ANGLE
    smooth_window = SQUAT_ANGLE_SMOOTH_WINDOW

    hud_angle_label = "Knee"
    ended_mid_rep_message = (
        "앉은 자세에서 영상이 끝나 마지막 동작 1회는 횟수에 포함되지 "
        "않았습니다. 완전히 일어선 뒤 촬영을 종료해 주세요."
    )
    partial_rep_message = (
        "충분히 앉지 못해 횟수에서 제외된 움직임이 {n}회 있습니다. 더 깊게 앉아 보세요."
    )
    not_side_view_message = (
        "측면 촬영이 아닌 것으로 보입니다. 옆에서 다시 촬영해 주세요. "
        "(정면 영상에서는 깊이·상체 판정이 부정확합니다)"
    )

    def __init__(self, fps: float | None = None) -> None:
        super().__init__(fps)
        # 프레임별 대퇴 거상각 원시값. 깊이는 최저점 단일 프레임이 아니라
        # 최저점 ±SQUAT_FEMUR_BOTTOM_WINDOW 프레임의 **중앙값**으로 판정한다.
        # 관절 좌표의 프레임 간 흔들림(로컬 실측 p95 8~13°)이 경계 근처 rep의
        # 판정을 뒤집는 것을 막는다. rep이 끝날 때마다 비운다.
        self._femur_by_frame: dict[int, float] = {}
        self._bottom_femur: float | None = None  # 이번 rep 판정에 쓴 평활 거상각
        # 완전히 선 자세의 거상각 표본(이론값 +90°). 카메라 기울기·개인별
        # 관절점 오프셋 보정(기립 캘리브레이션) 검토용으로 영상 전체에서 모은다.
        self._standing_femurs: list[float] = []

    def update(self, person: Person | None, frame_index: int) -> None:
        if person is not None:
            femur = mean_femur_elevation(person, _FEMURS)
            if femur is not None:
                self._femur_by_frame[frame_index] = femur
        super().update(person, frame_index)
        # super()가 평활 무릎각을 갱신한 뒤에 '선 자세' 여부를 판단한다.
        if (
            person is not None
            and self._last_angle is not None
            and self._last_angle > self.up_angle
            and frame_index in self._femur_by_frame
        ):
            self._standing_femurs.append(self._femur_by_frame[frame_index])

    def _reset_rep_tracking(self) -> None:
        super()._reset_rep_tracking()
        self._femur_by_frame.clear()
        self._bottom_femur = None

    def _smoothed_bottom_femur(self) -> float | None:
        """최저점 ±윈도 프레임의 대퇴 거상각 중앙값. 표본이 없으면 스냅샷 폴백."""
        values = [
            v for f, v in self._femur_by_frame.items()
            if abs(f - self._bottom_frame) <= SQUAT_FEMUR_BOTTOM_WINDOW
        ]
        if values:
            return statistics.median(values)
        if self._bottom_person is None:
            return None
        return mean_femur_elevation(self._bottom_person, _FEMURS)

    def measure_angle(self, person: Person) -> float | None:
        return _mid_knee_angle(person)

    def check_form(self, rep: int, bottom_person: Person | None,
                   min_angle: float) -> list[Issue]:
        """rep 최저점 자세를 측면 규칙(깊이·상체 앞숙임)으로 검사."""
        # 규칙 1: 깊이 (항상 판정). 1차 지표는 대퇴 거상각(최저점 ±윈도 중앙값,
        # record_bottom_measurements에서 계산해 둔 값과 동일)이고, 못 재는 rep에서만
        # 무릎각 예비 기준으로 판정한다.
        # (rep이 성립했다면 무릎각을 쟀다는 뜻이라 엉덩이·무릎은 보였지만,
        #  스냅샷 유실·좌표 겹침으로 거상각이 안 나오는 경우가 이론상 남는다)
        femur = self._bottom_femur
        if femur is None and bottom_person is not None:
            femur = mean_femur_elevation(bottom_person, _FEMURS)
        if femur is not None:
            issues = [check_depth_femur(femur, rep)]
        else:
            issues = [check_depth(min_angle, rep)]

        # 규칙 2: 최저점 스냅샷 기준 상체 앞숙임
        if bottom_person is not None:
            torso_issue = check_torso(bottom_person, rep)
            if torso_issue is not None:
                issues.append(torso_issue)
        return issues

    def record_bottom_measurements(self, record: RepRecord) -> None:
        """최저점 상체·정강이 기울기를 rep 기록에 남긴다(판정 여부와 무관).

        check_torso는 정상 범위면 Issue를 만들지 않아, 올바른 rep의 상체 값이
        리포트 어디에도 남지 않았다. 임계값을 실측 분포로 재검증하려면 결함이
        아닌 rep의 측정값이 필요하다. diff는 check_torso와 같은 순서로 반올림해
        판정에 쓰인 값과 어긋나지 않게 한다. (docs/SQUAT_TUNING.md §3)
        """
        if self._bottom_person is None:
            return
        # 깊이 판정에 실제로 쓰는 값(±윈도 중앙값)을 그대로 기록한다(기록=판정).
        femur = self._smoothed_bottom_femur()
        self._bottom_femur = femur
        if femur is not None:
            record.bottom_femur_elevation = round(femur, 1)
        # 판정에는 쓰지 않는 대안 지표(정규화 기준만 다름). 채택 검토용 측정값.
        span = mean_hip_in_shin_span(self._bottom_person, _LEGS)
        if span is not None:
            record.bottom_hip_in_span = round(span, 3)
        torso = _torso_lean(self._bottom_person)
        shin = _shin_incline(self._bottom_person)
        if torso is not None:
            record.bottom_torso_incline = round(torso, 1)
        if shin is not None:
            record.bottom_shin_incline = round(shin, 1)
        if torso is not None and shin is not None:
            record.bottom_torso_shin_diff = round(torso - shin, 1)

"""푸시업 분석기 (측면 촬영 전용).

스쿼트와 구조가 같다. 기준 관절각만 무릎 → **팔꿈치**로 바뀐다.
반복 카운트·최저점 스냅샷·유실 대응은 `base.AngleRepAnalyzer`가 처리하고,
이 파일에는 푸시업 규칙만 있다.

**측면 촬영 전용이며, 규칙은 측면 2D로 확실히 잴 수 있는 두 가지뿐이다.**

1. 깊이 — 최저점 팔꿈치각. 팔을 다 펴면 170~180°, 가슴이 바닥에 닿을 만큼
   내려가면 90° 이하로 접힌다.
2. 몸통 일직선 — 어깨-엉덩이-발목이 이루는 각. 180°에 가까워야 하고, 엉덩이가
   아래로 처지거나(허리 부담) 위로 솟으면(가동 범위 축소) 벗어난다.

손 간격·팔꿈치 벌어짐(flare)은 정면에서만 보이는 정보라 다루지 않는다.
근거와 촬영 가이드: docs/PUSHUP_CRITERIA.md
"""
from __future__ import annotations

import statistics

from ai.analysis.exercises.base import AngleRepAnalyzer
from ai.analysis.feedback import Issue, RepRecord, Severity
from ai.analysis.filters import MedianSmoother
from ai.analysis.landmarks import is_below_line, mean_joint_angle, visible_all
from ai.config import (
    PUSHUP_ADAPTIVE_DOWN_RATIO,
    PUSHUP_ADAPTIVE_MIN_SPAN,
    PUSHUP_ADAPTIVE_UP_RATIO,
    PUSHUP_ANGLE_SMOOTH_WINDOW,
    PUSHUP_BODY_LINE_SEVERE,
    PUSHUP_BODY_LINE_WARN,
    PUSHUP_ELBOW_DOWN_ANGLE,
    PUSHUP_ELBOW_UP_ANGLE,
    PUSHUP_GOOD_DEPTH_ANGLE,
    PUSHUP_PARTIAL_DIP_ANGLE,
    PUSHUP_SEVERE_DEPTH_ANGLE,
    PUSHUP_SIDE_VIEW_RATIO_MAX,
)
from ai.pose.detector import Person
from ai.pose.keypoints import KP

# 한쪽 팔 = (어깨, 팔꿈치, 손목)
_ARMS = {
    "left": (KP.LEFT_SHOULDER, KP.LEFT_ELBOW, KP.LEFT_WRIST),
    "right": (KP.RIGHT_SHOULDER, KP.RIGHT_ELBOW, KP.RIGHT_WRIST),
}
# 몸통 일직선 = (어깨, 엉덩이, 발목). 발목이 안 보이면 무릎까지로 대체한다
# (무릎 대고 하는 푸시업이거나 발이 프레임을 벗어난 경우).
_BODY_LINES = {
    "left": (KP.LEFT_SHOULDER, KP.LEFT_HIP, KP.LEFT_ANKLE),
    "right": (KP.RIGHT_SHOULDER, KP.RIGHT_HIP, KP.RIGHT_ANKLE),
}
_BODY_LINES_KNEE = {
    "left": (KP.LEFT_SHOULDER, KP.LEFT_HIP, KP.LEFT_KNEE),
    "right": (KP.RIGHT_SHOULDER, KP.RIGHT_HIP, KP.RIGHT_KNEE),
}


def _elbow_angle(person: Person) -> float | None:
    """양 팔꿈치각의 평균. 한쪽만 보이면 보이는 쪽만 사용."""
    return mean_joint_angle(person, _ARMS)


def _body_line_joints(person: Person) -> tuple[int, int, int] | None:
    """몸통 일직선을 잴 관절 3개. 발목 → (없으면) 무릎 순으로 고른다.

    좌우 중 먼저 보이는 쪽 하나만 쓴다(측면에서는 보통 한쪽만 보이고,
    좌우를 평균하면 어느 쪽 발목을 썼는지가 흐려져 방향 판정이 애매해진다).
    """
    for joints in (*_BODY_LINES.values(), *_BODY_LINES_KNEE.values()):
        if visible_all(person, joints):
            return joints
    return None


def _body_line_deviation(person: Person) -> tuple[float, bool | None] | None:
    """몸통 일직선 이탈각과 방향. 못 재면 None.

    반환: (이탈각(도), 엉덩이가 선보다 아래인가). 방향은 화면상 몸통 축이
    거의 수직이면(푸시업 자세가 아니면) None이 되어 '방향 불명'이 된다.
    """
    joints = _body_line_joints(person)
    if joints is None:
        return None
    shoulder, hip, far = joints
    angle = mean_joint_angle(person, {"only": joints})
    if angle is None:
        return None
    below = is_below_line(
        person[shoulder].as_xy(), person[far].as_xy(), person[hip].as_xy()
    )
    return (180.0 - angle, below)


# --- rep 최저점(bottom) 스냅샷 기준 순수 규칙 검사 -----------------------
# 스쿼트와 같은 규칙: 판정은 반올림한 표시값으로 내려 "측정값=기준값인데 결함"
# 같은 모순이 생기지 않게 한다(경계는 초과일 때만 승급).

def check_depth(min_elbow_angle: float, rep: int) -> Issue:
    """최저점 팔꿈치각으로 깊이를 판정. 항상 하나(좋음/부족/거의 안 내려감)를 반환."""
    measured = round(min_elbow_angle, 1)
    if measured > PUSHUP_SEVERE_DEPTH_ANGLE:
        return Issue(
            rep_index=rep, code="very_shallow_depth", severity=Severity.ERROR,
            message="거의 내려가지 않았습니다. 이번 회차는 가슴이 바닥에 닿을 만큼 "
                    "팔꿈치를 훨씬 더 굽히세요.",
            measured=measured, threshold=PUSHUP_SEVERE_DEPTH_ANGLE,
        )
    if measured > PUSHUP_GOOD_DEPTH_ANGLE:
        return Issue(
            rep_index=rep, code="shallow_depth", severity=Severity.WARNING,
            message="깊이가 조금 모자랍니다. 이번 회차는 팔꿈치가 직각이 될 때까지 "
                    "더 내려가세요.",
            measured=measured, threshold=PUSHUP_GOOD_DEPTH_ANGLE,
        )
    return Issue(
        rep_index=rep, code="good_depth", severity=Severity.GOOD,
        message="충분한 깊이로 잘 내려갔습니다.",
        measured=measured, threshold=PUSHUP_GOOD_DEPTH_ANGLE,
    )


def check_body_line(person: Person, rep: int) -> Issue | None:
    """몸통 일직선(어깨-엉덩이-발목). 이탈 방향에 따라 다른 교정을 안내한다.

    엉덩이가 처지면 허리가 눌리고, 솟으면 가동 범위가 줄어 깊이가 얕아진다.
    둘은 교정 방법이 반대라 문구를 갈라 준다.
    """
    measured = _body_line_deviation(person)
    if measured is None:
        return None  # 어깨·엉덩이·다리 중 하나라도 안 보이면 판정 보류
    deviation, below = measured
    deviation = round(deviation, 1)
    if deviation <= PUSHUP_BODY_LINE_WARN:
        return None

    if below is True:
        detail = ("엉덩이가 아래로 처졌습니다. 배와 엉덩이에 힘을 줘 "
                  "머리-엉덩이-발목을 한 직선으로 유지하세요.")
    elif below is False:
        detail = ("엉덩이가 위로 솟았습니다. 골반을 낮춰 "
                  "머리-엉덩이-발목을 한 직선으로 유지하세요.")
    else:
        # 화면상 몸통 축이 거의 수직 = 엎드린 자세로 보기 어렵다. 방향을
        # 단정하지 않고 이탈 사실만 알린다(값을 지어내지 않는다).
        detail = ("몸통이 일직선에서 벗어났습니다. 머리-엉덩이-발목을 한 직선으로 "
                  "유지하세요.")

    if deviation > PUSHUP_BODY_LINE_SEVERE:
        return Issue(
            rep_index=rep, code="excessive_body_line_break", severity=Severity.ERROR,
            message=detail, measured=deviation, threshold=PUSHUP_BODY_LINE_SEVERE,
        )
    return Issue(
        rep_index=rep, code="body_line_break", severity=Severity.WARNING,
        message=detail, measured=deviation, threshold=PUSHUP_BODY_LINE_WARN,
    )


class PushupAnalyzer(AngleRepAnalyzer):
    name = "푸시업"

    down_angle = PUSHUP_ELBOW_DOWN_ANGLE
    up_angle = PUSHUP_ELBOW_UP_ANGLE
    partial_dip_angle = PUSHUP_PARTIAL_DIP_ANGLE
    smooth_window = PUSHUP_ANGLE_SMOOTH_WINDOW

    hud_angle_label = "Elbow"
    side_view_ratio_max = PUSHUP_SIDE_VIEW_RATIO_MAX
    ended_mid_rep_message = (
        "내려간 자세에서 영상이 끝나 마지막 동작 1회는 횟수에 포함되지 않았습니다. "
        "팔을 완전히 펴고 올라온 뒤 촬영을 종료해 주세요."
    )
    partial_rep_message = (
        "충분히 내려가지 못해 횟수에서 제외된 움직임이 {n}회 있습니다. 더 깊게 내려가 보세요."
    )
    not_side_view_message = (
        "측면 촬영이 아닌 것으로 보입니다. 옆에서 다시 촬영해 주세요. "
        "(정면·머리쪽 영상에서는 깊이·몸통 판정이 부정확합니다)"
    )

    def __init__(self, fps: float | None = None) -> None:
        super().__init__(fps)
        # 적응 임계(아래 finalize 주석 참고)를 계산하려면 영상 전체의 각도 분포가
        # 필요하다. 그래서 프레임을 일단 모아 두고 finalize에서 한 번에 흘린다.
        self._buffer: list[tuple[int, Person | None]] = []
        self._calibrated = False

    def measure_angle(self, person: Person) -> float | None:
        return _elbow_angle(person)

    def update(self, person: Person | None, frame_index: int) -> None:
        """보정 전에는 프레임을 모으기만 한다(판정은 finalize에서 일괄 수행)."""
        if self._calibrated:
            super().update(person, frame_index)
        else:
            self._buffer.append((frame_index, person))

    def _calibrate(self) -> None:
        """이 영상의 팔꿈치각 분포에서 DOWN/UP 임계를 정한다.

        고정 임계가 실패하는 이유는 절대각의 기준점이 영상마다 다르기 때문이다.
        팔을 다 편 자세인데도 측정값이 149°에 그치는 영상이 있어, 160°를 UP 기준으로
        두면 그 영상은 rep이 하나도 안 세어진다(실측 7편 중 3편이 0회였다).

        그래서 '이 사람의 이 영상에서 팔을 편 상태와 접은 상태'를 분포로 잡고
        그 사이에 임계를 둔다. 폭이 너무 좁으면(반복 동작이 없는 영상) 잔떨림을
        rep으로 세게 되므로 적응을 끄고 고정 임계로 돌아간다.
        """
        smoother = MedianSmoother(self.smooth_window)
        angles = [
            smoother.push(angle)
            for _idx, person in self._buffer
            if person is not None
            if (angle := self.measure_angle(person)) is not None
        ]
        if len(angles) < 20:
            return  # 표본 부족 — 고정 임계 유지
        q = statistics.quantiles(angles, n=100)
        low, high = q[4], q[94]          # p5 ~ p95 (양 끝 이상치 제외)
        span = high - low
        if span < PUSHUP_ADAPTIVE_MIN_SPAN:
            return  # 반복 동작으로 볼 만한 폭이 아니다 — 고정 임계 유지
        self.down_angle = low + PUSHUP_ADAPTIVE_DOWN_RATIO * span
        self.up_angle = low + PUSHUP_ADAPTIVE_UP_RATIO * span
        self.partial_dip_angle = (self.down_angle + self.up_angle) / 2

    def finalize(self):
        if not self._calibrated:
            self._calibrate()
            self._calibrated = True
            buffered, self._buffer = self._buffer, []
            for frame_index, person in buffered:
                super().update(person, frame_index)
        return super().finalize()

    def check_form(self, rep: int, bottom_person: Person | None,
                   min_angle: float) -> list[Issue]:
        """rep 최저점 자세를 측면 규칙(깊이·몸통 일직선)으로 검사."""
        issues = [check_depth(min_angle, rep)]  # 깊이는 항상 판정
        if bottom_person is not None:
            body_issue = check_body_line(bottom_person, rep)
            if body_issue is not None:
                issues.append(body_issue)
        return issues

    def record_bottom_measurements(self, record: RepRecord) -> None:
        """최저점 몸통 이탈각을 판정 여부와 무관하게 남긴다.

        정상 rep의 이탈각이 실제로 몇 도인지 모르면 15°/25°가 맞는지 검증할 수
        없다. 스쿼트의 상체 측정값과 같은 이유다(docs/SQUAT_TUNING.md §3).
        """
        if self._bottom_person is None:
            return
        measured = _body_line_deviation(self._bottom_person)
        if measured is not None:
            record.bottom_body_line_dev = round(measured[0], 1)

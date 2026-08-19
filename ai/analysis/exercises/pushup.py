"""푸시업 분석기 (측면 촬영 전용).

스쿼트와 구조가 같다. 기준 관절각만 무릎 → **팔꿈치**로 바뀐다.
반복 카운트·최저점 스냅샷·유실 대응은 `base.AngleRepAnalyzer`가 처리하고,
이 파일에는 푸시업 규칙만 있다.

**측면 촬영 전용이며, 규칙은 측면 2D로 확실히 잴 수 있는 두 가지뿐이다.**

1. 깊이 — 최저점 팔꿈치각. 팔을 다 펴면 170~180°, 가슴이 바닥에 닿을 만큼
   내려가면 90° 이하로 접힌다.
2. 몸통 일직선 — 어깨-엉덩이-발목 이탈각. **절대각으로는 판정하지 않는다**
   (실사용 조건에서 곧은 몸도 수십 도로 읽힘 — docs/PUSHUP_TUNING.md §9).
   대신 영상 앞부분(첫 dip 이전)의 top 자세에서 그 사람·그 카메라의 기준
   이탈각을 캘리브레이션하고, 이후 rep은 **기준선 대비 부호 있는 변화량**
   (+처짐/−솟음)으로 판정한다. 기준선을 못 재면(운동 중에 시작한 영상)
   판정을 보류하고 촬영 안내(no_body_baseline)만 낸다.

손 간격·팔꿈치 벌어짐(flare)은 정면에서만 보이는 정보라 다루지 않는다.
근거와 촬영 가이드: docs/PUSHUP_CRITERIA.md
"""
from __future__ import annotations

import statistics

from ai.analysis.exercises.base import AngleRepAnalyzer
from ai.analysis.feedback import Issue, RepRecord, Severity
from ai.analysis.filters import MedianSmoother
from ai.analysis.landmarks import (
    hip_gap_ratio,
    is_below_line,
    mean_joint_angle,
    torso_horizontality,
    torso_length,
    visible_all,
)
from ai.config import (
    PUSHUP_ADAPTIVE_DOWN_RATIO,
    PUSHUP_ADAPTIVE_MIN_SPAN,
    PUSHUP_ADAPTIVE_UP_RATIO,
    PUSHUP_ANGLE_SMOOTH_WINDOW,
    PUSHUP_ANKLE_ABOVE_KNEE_MAX,
    PUSHUP_BODY_CALIB_MAX_SD,
    PUSHUP_BODY_CALIB_MIN_SAMPLES,
    PUSHUP_BODY_CALIB_TAIL,
    PUSHUP_BODY_DELTA_SEVERE,
    PUSHUP_BODY_DELTA_WARN,
    PUSHUP_BODY_LINE_SEVERE,
    PUSHUP_BODY_LINE_WARN,
    PUSHUP_ELBOW_DOWN_ANGLE,
    PUSHUP_ELBOW_UP_ANGLE,
    PUSHUP_GOOD_DEPTH_ANGLE,
    PUSHUP_PARTIAL_DIP_ANGLE,
    PUSHUP_REP_PROMINENCE,
    PUSHUP_SEVERE_DEPTH_ANGLE,
    PUSHUP_SIDE_VIEW_RATIO_MAX,
    PUSHUP_SMOOTH_WINDOW_FALLBACK,
    PUSHUP_TOP_BODY_WINDOW,
    PUSHUP_VIEW_HIP_GAP_MAX,
    PUSHUP_VIEW_HORIZ_MIN,
    SIDE_VIEW_MIN_SAMPLES,
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


def _body_line_joints(person: Person,
                      prefer_knee: bool = False) -> tuple[int, int, int] | None:
    """몸통 일직선을 잴 관절 3개. 기본은 발목 → (없으면) 무릎 순.

    좌우 중 먼저 보이는 쪽 하나만 쓴다(측면에서는 보통 한쪽만 보이고,
    좌우를 평균하면 어느 쪽 발목을 썼는지가 흐려져 방향 판정이 애매해진다).

    prefer_knee=True면 무릎을 먼저 쓴다. 발을 공중에 든 무릎 푸시업에서는
    발목이 몸통 선의 끝점이 아니고(MM-Fit w19 실관측), 곧은 몸에서는 무릎도
    같은 직선 위라 무릎 측정이 항상 안전하다. **끝점은 영상 단위로 한 번만
    정한다**(PushupAnalyzer._decide_body_endpoint) — 프레임마다 발목/무릎이
    오가면 캘리브레이션 표준편차가 튀어 기준선이 통째로 죽는다(실측:
    clip_4804794, 앞사선 원근으로 발목이 무릎 위로 투영되는 정상 영상).
    """
    triples = ((*_BODY_LINES_KNEE.values(), *_BODY_LINES.values())
               if prefer_knee
               else (*_BODY_LINES.values(), *_BODY_LINES_KNEE.values()))
    for joints in triples:
        if visible_all(person, joints):
            return joints
    return None


def _body_line_deviation(person: Person, prefer_knee: bool = False,
                         ) -> tuple[float, bool | None] | None:
    """몸통 일직선 이탈각과 방향. 못 재면 None.

    반환: (이탈각(도), 엉덩이가 선보다 아래인가). 방향은 화면상 몸통 축이
    거의 수직이면(푸시업 자세가 아니면) None이 되어 '방향 불명'이 된다.
    """
    joints = _body_line_joints(person, prefer_knee)
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


def check_body_line_values(deviation: float, below: bool | None,
                           rep: int) -> Issue | None:
    """몸통 일직선 판정의 순수 규칙부. 측정값(이탈각·방향)을 받아 Issue를 낸다.

    엉덩이가 처지면 허리가 눌리고, 솟으면 가동 범위가 줄어 깊이가 얕아진다.
    둘은 교정 방법이 반대라 문구를 갈라 준다.
    """
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


def check_body_line(person: Person, rep: int) -> Issue | None:
    """관절 스냅샷 한 장을 절대 임계값으로 판정하는 **비활성** 경로.

    프로덕션 판정은 기준선 대비 델타(check_body_delta_value)다. 이 함수는
    절대각 규칙의 재검증·단위 테스트용으로만 남아 있다(check_form이 안 부른다).
    """
    measured = _body_line_deviation(person)
    if measured is None:
        return None  # 어깨·엉덩이·다리 중 하나라도 안 보이면 판정 보류
    return check_body_line_values(measured[0], measured[1], rep)


def check_body_delta_value(delta: float, rep: int) -> Issue | None:
    """기준선 대비 몸통 이탈 변화량(부호: +처짐/−솟음)을 판정하는 순수 규칙부.

    절대각 대신 델타를 쓰는 이유: 촬영·체형별 고정 편차(곧은 몸도 1.3~48.9°)가
    결함 신호보다 커서 절대 임계값이 성립하지 않는다. 기준선을 빼면 그 편차가
    0으로 접히고, 남는 잡음 바닥(rep 간 변동 P90 ≈ 8°) 위에서 판정할 수 있다.
    근거·잠정 임계값: ai/config.py PUSHUP_BODY_DELTA_* 주석.

    measured에는 |델타|를 담는다(임계값과 같은 축 — '초과가 결함' 관례 유지).
    방향은 문구로 전달한다.
    """
    magnitude = round(abs(delta), 1)
    if magnitude <= PUSHUP_BODY_DELTA_WARN:
        return None

    if delta > 0:
        detail = ("운동을 시작할 때보다 엉덩이가 아래로 처졌습니다. 배와 엉덩이에 "
                  "힘을 줘 머리-엉덩이-발목을 한 직선으로 유지하세요.")
    else:
        detail = ("운동을 시작할 때보다 엉덩이가 위로 솟았습니다. 골반을 낮춰 "
                  "머리-엉덩이-발목을 한 직선으로 유지하세요.")

    if magnitude > PUSHUP_BODY_DELTA_SEVERE:
        return Issue(
            rep_index=rep, code="excessive_body_line_break", severity=Severity.ERROR,
            message=detail, measured=magnitude, threshold=PUSHUP_BODY_DELTA_SEVERE,
        )
    return Issue(
        rep_index=rep, code="body_line_break", severity=Severity.WARNING,
        message=detail, measured=magnitude, threshold=PUSHUP_BODY_DELTA_WARN,
    )


class PushupAnalyzer(AngleRepAnalyzer):
    name = "푸시업"

    down_angle = PUSHUP_ELBOW_DOWN_ANGLE
    up_angle = PUSHUP_ELBOW_UP_ANGLE
    partial_dip_angle = PUSHUP_PARTIAL_DIP_ANGLE
    smooth_window = PUSHUP_ANGLE_SMOOTH_WINDOW
    rep_prominence = PUSHUP_REP_PROMINENCE

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
        "바닥 푸시업을 옆에서 촬영한 영상이 아닌 것으로 보입니다. 바닥에 엎드린 "
        "푸시업을 완전한 측면에서 다시 촬영해 주세요. "
        "(정면·머리쪽·벽/인클라인 영상에서는 깊이·몸통 판정이 부정확합니다)"
    )

    def __init__(self, fps: float | None = None) -> None:
        super().__init__(fps)
        # 적응 임계(아래 finalize 주석 참고)를 계산하려면 영상 전체의 각도 분포가
        # 필요하다. 그래서 프레임을 일단 모아 두고 finalize에서 한 번에 흘린다.
        self._buffer: list[tuple[int, Person | None]] = []
        self._calibrated = False
        # top(팔 편) 자세 프레임의 몸통 이탈각. 몸통 판정의 1차 지표다 —
        # 최저점 스냅샷은 완전 하강에서 기하학적으로 과탐한다(ai/config.py의
        # PUSHUP_TOP_BODY_WINDOW 주석과 docs/PUSHUP_TUNING.md §9).
        self._top_devs: list[tuple[int, float, bool | None]] = []
        # 몸통 기준선 캘리브레이션: 첫 dip 이전 top 자세의 부호 이탈각 표본과,
        # 거기서 계산한 이 영상의 기준선(+처짐/−솟음). 기준선이 None이면
        # 델타 판정 전체가 보류된다(ai/config.py PUSHUP_BODY_CALIB_* 주석).
        self._calib_devs: list[float] = []
        self._movement_seen = False
        self.body_line_baseline: float | None = None
        # 3중 측면 게이트의 추가 표본(기본 어깨 지표는 base가 모은다).
        self._hip_gaps: list[float] = []
        self._horiz: list[float] = []
        # 몸통 선 끝점(발목/무릎)은 영상 단위로 한 번 정한다(_decide_body_endpoint).
        self._prefer_knee = False

    def measure_angle(self, person: Person) -> float | None:
        return _elbow_angle(person)

    def _process_frame(self, person: Person | None, frame_index: int) -> None:
        """상태기계 갱신 + 측면 게이트 표본 + top 자세 몸통 이탈각 수집."""
        super().update(person, frame_index)
        if person is None:
            return
        gap = hip_gap_ratio(person)
        if gap is not None:
            self._hip_gaps.append(gap)
        horiz = torso_horizontality(person)
        if horiz is not None:
            self._horiz.append(horiz)
        if self._last_angle is None:
            return
        if self._last_angle > self.up_angle:
            measured = _body_line_deviation(person, self._prefer_knee)
            if measured is not None:
                self._top_devs.append((frame_index, measured[0], measured[1]))
                # 첫 dip 이전의 top 자세 = 몸통 기준선 캘리브레이션 구간.
                # (방향을 모르는 표본은 부호를 매길 수 없어 기준선에서 뺀다)
                if not self._movement_seen and measured[1] is not None:
                    self._calib_devs.append(
                        measured[0] if measured[1] else -measured[0])
                # 판정에는 최근 표본만 쓰므로 무한히 쌓을 필요가 없다.
                if len(self._top_devs) > 10 * PUSHUP_TOP_BODY_WINDOW:
                    del self._top_devs[:-2 * PUSHUP_TOP_BODY_WINDOW]
        elif not self._movement_seen:
            # 팔을 굽히기 시작 → 캘리브레이션 구간 종료. 여기서 기준선을 확정해야
            # 이후 _top_devs가 잘려 나가도(위의 del) 기준선이 흔들리지 않는다.
            #
            # 기준선 = 꼬리(첫 dip 직전 = 실제 플랭크 자세) 중앙값. 구간 전체를
            # 쓰면 플랭크 진입 전 준비 동작에 오염된다. 꼬리가 안정적이지 않으면
            # (sd 초과 = 측정 표류 영상) 기준선을 세우지 않는다 — 어떤 기준선도
            # 오탐을 막지 못한다는 것이 로컬 실측 결론이다(ai/config.py 주석).
            self._movement_seen = True
            if len(self._calib_devs) >= PUSHUP_BODY_CALIB_MIN_SAMPLES:
                tail = self._calib_devs[-PUSHUP_BODY_CALIB_TAIL:]
                if statistics.stdev(tail) <= PUSHUP_BODY_CALIB_MAX_SD:
                    self.body_line_baseline = round(statistics.median(tail), 1)
                    self.report.body_line_baseline = self.body_line_baseline

    def _top_body_line_snapshot(self) -> tuple[float, bool | None] | None:
        """이번 rep 최저점 이전 top 프레임들의 (이탈각 중앙값, 다수 방향).

        표본이 없으면 None. 크기 기록(top_body_line_dev)용이다.
        """
        before = [t for t in self._top_devs if t[0] < self._bottom_frame]
        window = before[-PUSHUP_TOP_BODY_WINDOW:]
        if not window:
            return None
        deviation = statistics.median(v for _, v, _ in window)
        belows = [b for _, _, b in window if b is not None]
        below: bool | None = None
        if belows:
            trues = sum(belows)
            if trues * 2 != len(belows):  # 동수면 방향 불명으로 남긴다
                below = trues * 2 > len(belows)
        return (deviation, below)

    # 델타 판정에 필요한 최소 부호 표본 수. 단일 프레임의 이탈각은 잡음이
    # 수 도라(로컬 실측 rep 간 sd 2~8°) 한두 장 중앙값으로 판정을 내리지 않는다.
    _MIN_SIGNED_SAMPLES = 3

    def _top_body_line_delta(self) -> float | None:
        """이번 rep의 top 부호 이탈각(중앙값)에서 기준선을 뺀 변화량.

        기준선이 없거나 이번 rep의 부호 표본이 부족하면 None(판정 보류).
        """
        if self.body_line_baseline is None:
            return None
        before = [t for t in self._top_devs if t[0] < self._bottom_frame]
        window = before[-PUSHUP_TOP_BODY_WINDOW:]
        signed = [dev if below else -dev
                  for _, dev, below in window if below is not None]
        if len(signed) < self._MIN_SIGNED_SAMPLES:
            return None
        return statistics.median(signed) - self.body_line_baseline

    def update(self, person: Person | None, frame_index: int) -> None:
        """보정 전에는 프레임을 모으기만 한다(판정은 finalize에서 일괄 수행)."""
        if self._calibrated:
            self._process_frame(person, frame_index)
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
        def spread(window: int) -> tuple[list[float], float, float, float] | None:
            """buffer를 주어진 윈도로 평활한 (각도열, p5, p95, 폭)."""
            smoother = MedianSmoother(window)
            angles = [
                smoother.push(angle)
                for _idx, person in self._buffer
                if person is not None
                if (angle := self.measure_angle(person)) is not None
            ]
            if len(angles) < 20:
                return None  # 표본 부족
            q = statistics.quantiles(angles, n=100)
            return angles, q[4], q[94], q[94] - q[4]  # p5~p95 (이상치 제외)

        def transitions(angles: list[float], low: float, span: float) -> int:
            """이 임계로 상태기계를 돌리면 몇 rep이 나오는지 미리 세어 본다.

            update()의 카운트 규칙(히스테리시스 + 깊이 가드)과 같은 조건이다.
            윈도가 dip을 뭉개면 폭은 남아도 전이가 0이 될 수 있다(RTExR 실측:
            similar_57f76c55 — 폭 49°인데 0회).
            """
            down = low + PUSHUP_ADAPTIVE_DOWN_RATIO * span
            up = low + PUSHUP_ADAPTIVE_UP_RATIO * span
            state, min_angle, n = "UP", 180.0, 0
            for angle in angles:
                if state == "UP" and angle < down:
                    state, min_angle = "DOWN", angle
                elif state == "DOWN":
                    min_angle = min(min_angle, angle)
                    if angle > up:
                        state = "UP"
                        if min_angle <= down - self.rep_prominence:
                            n += 1
            return n

        measured = spread(self.smooth_window)
        if measured is None:
            return  # 표본 부족 — 고정 임계 유지
        angles, low, high, span = measured
        # 기본 윈도가 dip을 지웠다는 두 가지 징후에서 좁은 윈도를 시험한다
        # (빠른 템포 + 낮은 fps — ai/config.py PUSHUP_SMOOTH_WINDOW_FALLBACK):
        #   ① 평활 폭 붕괴(< MIN_SPAN)  ② 폭은 남았지만 rep 전이가 0
        # 어느 쪽이든 현재 상태로는 0회가 되는 영상이라, 좁은 윈도가 반복을
        # 살려낼 때만 채택하는 이 폴백은 결과를 악화시킬 수 없다.
        suspect = span < PUSHUP_ADAPTIVE_MIN_SPAN \
            or transitions(angles, low, span) == 0
        if suspect:
            narrow = spread(PUSHUP_SMOOTH_WINDOW_FALLBACK)
            rescued = (
                narrow is not None
                and narrow[3] >= PUSHUP_ADAPTIVE_MIN_SPAN
                and transitions(narrow[0], narrow[1], narrow[3]) > 0
            )
            if rescued:
                angles, low, high, span = narrow
                self.smooth_window = PUSHUP_SMOOTH_WINDOW_FALLBACK
                self._smoother = MedianSmoother(self.smooth_window)
            elif span < PUSHUP_ADAPTIVE_MIN_SPAN:
                return  # 어느 윈도로도 반복 폭이 아니다 — 고정 임계 유지
        self.down_angle = low + PUSHUP_ADAPTIVE_DOWN_RATIO * span
        self.up_angle = low + PUSHUP_ADAPTIVE_UP_RATIO * span
        self.partial_dip_angle = (self.down_angle + self.up_angle) / 2

    def _side_view_issue(self) -> Issue | None:
        """3중 측면 게이트: 어깨 간격(기본) + 골반 간격 + 몸통 수평도.

        어깨 지표 하나로는 측면/정면 분포가 겹쳐 실패했다(§7-B). 지표별 근거
        분포는 ai/config.py PUSHUP_VIEW_* 주석. 하나라도 걸리면 재촬영 안내를
        낸다. 잔존 한계: 낮은 사선 근접 촬영은 세 지표 모두 측면과 겹친다.
        """
        issue = super()._side_view_issue()
        if issue is not None:
            return issue

        def _made(measured: float, threshold: float) -> Issue:
            # 어느 지표에 걸렸는지는 threshold 값으로 구분된다(사용자 문구는 동일).
            return Issue(
                rep_index=0, code="not_side_view", severity=Severity.ERROR,
                message=self.not_side_view_message,
                measured=round(measured, 2), threshold=threshold,
            )

        if len(self._hip_gaps) >= SIDE_VIEW_MIN_SAMPLES:
            gap = statistics.median(self._hip_gaps)
            if gap > PUSHUP_VIEW_HIP_GAP_MAX:
                return _made(gap, PUSHUP_VIEW_HIP_GAP_MAX)
        if len(self._horiz) >= SIDE_VIEW_MIN_SAMPLES:
            horiz = statistics.median(self._horiz)
            if horiz < PUSHUP_VIEW_HORIZ_MIN:
                return _made(horiz, PUSHUP_VIEW_HORIZ_MIN)
        return None

    def _decide_body_endpoint(self, buffered) -> None:
        """몸통 선 끝점(발목/무릎)을 영상 전체 다수결로 한 번만 정한다.

        발목이 무릎보다 뚜렷이 위인 프레임이 과반이면 무릎을 쓴다 —
        발을 공중에 든 무릎 푸시업(발목이 몸통 선 밖)과, 앞사선 원근으로
        발목이 떠 보이는 영상(무릎 측정도 유효)을 같은 규칙이 처리한다.
        프레임 단위로 정하면 끝점이 오가며 캘리브레이션이 죽는다.
        기준·실측 분포: ai/config.py PUSHUP_ANKLE_ABOVE_KNEE_MAX 주석.
        """
        raised = total = 0
        for _idx, person in buffered:
            if person is None:
                continue
            torso = torso_length(person)
            if not torso:
                continue
            for (_sh, _hip, ankle), (_s2, _h2, knee) in zip(
                    _BODY_LINES.values(), _BODY_LINES_KNEE.values()):
                if not (person[ankle].visible and person[knee].visible):
                    continue
                total += 1
                if (person[knee].y - person[ankle].y
                        ) > PUSHUP_ANKLE_ABOVE_KNEE_MAX * torso:
                    raised += 1
        self._prefer_knee = total >= SIDE_VIEW_MIN_SAMPLES \
            and raised * 2 > total

    def finalize(self):
        if not self._calibrated:
            self._calibrate()
            self._calibrated = True
            buffered, self._buffer = self._buffer, []
            self._decide_body_endpoint(buffered)
            for frame_index, person in buffered:
                self._process_frame(person, frame_index)
        # 무릎 끝점 모드(발 든 무릎 푸시업 또는 발목이 떠 보이는 촬영 각도)에서는
        # 몸통 델타 판정을 보류했다 — 조용히 빼지 않고 사유를 안내한다.
        if self.report.rep_count and self._prefer_knee:
            self.report.add_video_issue(Issue(
                rep_index=0, code="body_line_unverified", severity=Severity.WARNING,
                message=("발 위치가 일반 푸시업과 달라(발을 들었거나 촬영 각도 상 "
                         "발목 위치를 신뢰할 수 없어) 몸통 일직선 분석을 제공하지 "
                         "않았습니다. 발끝을 바닥에 대고 완전한 측면에서 촬영하면 "
                         "몸통 처짐·솟음 분석이 제공됩니다."),
            ))
        # 몸통 기준선을 못 잡았으면(첫 dip 전 top 구간 부족) 몸통 판정이 통째로
        # 보류된 것이다. 조용히 빼지 않고, 다음 촬영에서 얻는 법을 안내한다.
        elif self.report.rep_count and self.body_line_baseline is None:
            self.report.add_video_issue(Issue(
                rep_index=0, code="no_body_baseline", severity=Severity.WARNING,
                message=("운동 시작 전 기준 자세가 잡히지 않아 몸통 일직선 분석을 "
                         "할 수 없었습니다. 촬영을 시작한 뒤 팔을 편 플랭크 자세로 "
                         "2~3초 움직임 없이 멈췄다가 운동을 시작하면 몸통 처짐·솟음 "
                         "분석이 제공됩니다."),
                measured=float(len(self._calib_devs)),
                threshold=float(PUSHUP_BODY_CALIB_MIN_SAMPLES),
            ))
        return super().finalize()

    def check_form(self, rep: int, bottom_person: Person | None,
                   min_angle: float) -> list[Issue]:
        """깊이(절대 기준) + 몸통(기준선 대비 델타)을 판정한다.

        몸통 이탈각의 **절대각 판정은 세 데이터셋에서 실패가 확인돼 하지 않는다**
        (곧은 몸도 48~137.6°로 읽힘 — docs/PUSHUP_TUNING.md §9). 대신 첫 dip
        이전 top 자세로 캘리브레이션한 기준선 대비 부호 변화량으로 판정한다.
        기준선이 없으면(운동 중에 시작한 영상) 몸통 판정은 보류되고 finalize가
        촬영 안내(no_body_baseline)를 낸다.

        구조적 한계: rep 1의 top 표본은 캘리브레이션 구간과 겹쳐 델타가 0에
        가깝다(자기 기준 판정의 본질). 시작부터 존재하는 만성 처짐도 기준선에
        흡수된다 — 앱의 시작 자세 안내가 전제다.
        """
        issues = [check_depth(min_angle, rep)]  # 깊이는 항상 판정
        # 무릎 끝점 모드에서는 델타 판정을 보류한다(측정은 record_*가 남긴다).
        # 델타 임계 15°/25°는 발목 기준 잡음 바닥(P90≈8°)으로 튜닝된 값인데,
        # 무릎은 지렛대가 짧아 같은 엉덩이 흔들림이 더 큰 각도로 읽힌다
        # (clip_4804794 실측: 발목 기준 무발화 → 무릎 기준 오탐). 무릎 기준
        # 임계는 결함 라벨 데이터가 생기기 전까지 세우지 않는다.
        if not self._prefer_knee:
            delta = self._top_body_line_delta()
            if delta is not None:
                issue = check_body_delta_value(delta, rep)
                if issue is not None:
                    issues.append(issue)
        return issues

    def record_bottom_measurements(self, record: RepRecord) -> None:
        """몸통 이탈각을 판정 여부와 무관하게 남긴다.

        델타(top_body_line_delta)는 판정에 실제로 쓰는 지표(기록=판정),
        top·최저점 크기는 임계값 재검증·완전 하강 왜곡 연구용 기록이다
        (docs/SQUAT_TUNING.md §3과 같은 원칙).
        """
        top = self._top_body_line_snapshot()
        if top is not None:
            record.top_body_line_dev = round(top[0], 1)
        delta = self._top_body_line_delta()
        if delta is not None:
            record.top_body_line_delta = round(delta, 1)
        if self._bottom_person is None:
            return
        measured = _body_line_deviation(self._bottom_person, self._prefer_knee)
        if measured is not None:
            record.bottom_body_line_dev = round(measured[0], 1)

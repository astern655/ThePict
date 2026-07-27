"""AI 분석 로직 단독 검증 (측면 촬영 전용).

YOLO도 영상도 없이, 가짜 관절 좌표를 만들어 넣어
'각도 계산 → 평활화 → 상태기계 → 반복 카운트 → 자세 판정'이 맞는지 확인한다.
실행: python -m tests.test_squat_logic

시퀀스는 실제 영상처럼 여러 프레임에 걸쳐 완만하게 변한다.
(중앙값 필터가 단일 프레임 스파이크를 의도적으로 제거하기 때문)
"""
from __future__ import annotations

import math

from ai.analysis.exercises.squat import SquatAnalyzer, check_depth, check_torso
from ai.analysis.feedback import RepVerdict, Severity
from ai.analysis.geometry import angle_at
from ai.pose.keypoints import KP, Keypoint

# 정상 스쿼트 1회: 서 있음 → 완만히 내려감 → 최저점(80도) 유지 → 완만히 일어섬
CLEAN_REP = [170, 170, 150, 130, 110, 95, 85, 80, 80, 85, 95, 110, 130, 150, 165, 175, 175]
# 얕은 스쿼트 1회: 최저점이 105도까지만 내려감 (rep으로는 세되 깊이 부족 경고)
SHALLOW_REP = [170, 170, 160, 150, 135, 120, 105, 105, 120, 135, 150, 165, 175, 175]
# 거의 앉지 않은 1회: 최저점 132도로 심각 임계(110도)를 넘어 ERROR
VERY_SHALLOW_REP = [170, 170, 160, 150, 138, 132, 132, 138, 150, 165, 175, 175]


def _blank() -> list[Keypoint]:
    """전부 안 보이는(conf 0) 관절 17개."""
    return [Keypoint(0.0, 0.0, 0.0) for _ in range(17)]


def _set(kp: list[Keypoint], **points: tuple[float, float]) -> list[Keypoint]:
    """KP 이름별 좌표를 넣고 visible(conf 0.9) 하게 만든다. 예: _set(kp, LEFT_KNEE=(0,0))."""
    for name, (x, y) in points.items():
        kp[getattr(KP, name)] = Keypoint(x, y, 0.9)
    return kp


def _hip_for_angle(knee: tuple[float, float], ankle: tuple[float, float], angle_deg: float) -> tuple[float, float]:
    """무릎각이 angle_deg가 되도록 엉덩이 위치를 만든다.

    무릎→발목 방향을 angle_deg 만큼 회전시켜 무릎→엉덩이 방향으로 삼는다.
    그러면 angle_at(hip, knee, ankle) == angle_deg.
    """
    ax, ay = ankle[0] - knee[0], ankle[1] - knee[1]
    length = math.hypot(ax, ay)
    ux, uy = ax / length, ay / length
    th = math.radians(angle_deg)
    hx = knee[0] + (ux * math.cos(th) - uy * math.sin(th)) * 100.0
    hy = knee[1] + (ux * math.sin(th) + uy * math.cos(th)) * 100.0
    return (hx, hy)


def _upright_person(knee_angle_deg: float) -> list[Keypoint]:
    """상체를 곧게 세운 정상 자세. 무릎각만 원하는 값으로 준다.

    어깨가 엉덩이 바로 위(같은 x)라 상체 기울기 0도 → torso_lean에 걸리지 않는다.
    """
    knee = (300.0, 300.0)
    ankle = (300.0, 400.0)  # 무릎 바로 아래
    hip = _hip_for_angle(knee, ankle, knee_angle_deg)
    return _set(
        _blank(),
        LEFT_HIP=hip, LEFT_KNEE=knee, LEFT_ANKLE=ankle,
        LEFT_SHOULDER=(hip[0], hip[1] - 100.0),
    )


def _leaning_person(knee_angle_deg: float) -> list[Keypoint]:
    """상체가 앞으로 숙여진 자세(측면 torso_lean 형태, WARNING 범위).

    정강이는 수직(무릎이 발목 바로 위)이므로 상체−정강이 차이 = 상체 기울기.
    어깨가 엉덩이보다 앞(x+121)·위(y-180)로 나가 약 34도 → 30~40도 WARNING 구간.
    """
    knee = (300.0, 300.0)
    ankle = (300.0, 400.0)
    hip = _hip_for_angle(knee, ankle, knee_angle_deg)
    return _set(
        _blank(),
        LEFT_HIP=hip, LEFT_KNEE=knee, LEFT_ANKLE=ankle,
        LEFT_SHOULDER=(hip[0] + 121.0, hip[1] - 180.0),
    )


def _torso_person(lean_deg: float, shin_deg: float | None = 0.0) -> list[Keypoint]:
    """상체·정강이 기울기를 지정한 관절 배치(check_torso 단독 테스트용).

    shin_deg=None이면 다리를 아예 숨겨 '정강이가 안 보이는' 경우를 만든다.
    """
    hip = (300.0, 250.0)
    lean = math.radians(lean_deg)
    kp = _set(
        _blank(),
        LEFT_HIP=hip,
        LEFT_SHOULDER=(hip[0] + 120.0 * math.sin(lean), hip[1] - 120.0 * math.cos(lean)),
    )
    if shin_deg is not None:
        ankle = (300.0, 400.0)
        shin = math.radians(shin_deg)
        kp = _set(
            kp,
            LEFT_ANKLE=ankle,
            LEFT_KNEE=(ankle[0] + 100.0 * math.sin(shin), ankle[1] - 100.0 * math.cos(shin)),
        )
    return kp


# --- 순수 계산 ----------------------------------------------------------

def test_angle_math() -> None:
    a, b, c = (0.0, 0.0), (0.0, 1.0), (1.0, 1.0)
    assert abs(angle_at(a, b, c) - 90.0) < 1e-6            # 직각
    assert abs(angle_at((0.0, 0.0), (0.0, 1.0), (0.0, 2.0)) - 180.0) < 1e-6  # 일직선
    print("✅ angle_at 계산 정확")


# --- 반복 카운트 --------------------------------------------------------

def test_rep_counting() -> None:
    analyzer = SquatAnalyzer()
    sequence = CLEAN_REP * 3
    for i, ang in enumerate(sequence):
        analyzer.update(_upright_person(ang), i)
    report = analyzer.finalize()
    assert report.rep_count == 3, f"기대 3회, 실제 {report.rep_count}회"
    assert report.partial_rep_count == 0
    print(f"✅ 반복 카운트 정확: {report.rep_count}회")


def test_shallow_rep_counted_with_warning() -> None:
    """얕은 스쿼트도 rep으로 세되 shallow_depth 경고를 붙인다."""
    analyzer = SquatAnalyzer()
    for i, ang in enumerate(SHALLOW_REP):
        analyzer.update(_upright_person(ang), i)
    report = analyzer.finalize()
    assert report.rep_count == 1, f"기대 1회, 실제 {report.rep_count}회"
    codes = {i.code for i in report.issues_for_rep(1)}
    assert "shallow_depth" in codes, f"깊이 부족을 못 잡음: {codes}"
    assert report.rep_verdict(1) is RepVerdict.NEEDS_WORK
    print("✅ 얕은 스쿼트 → rep으로 세고 '깊이 부족' 경고")


# --- 자세 규칙(순수 함수) -----------------------------------------------

def test_torso_rule_relative_to_shin() -> None:
    """상체 앞숙임은 절대각이 아니라 상체−정강이 차이로 판정한다."""
    # 정강이 수직 기준: 차이 31° → WARNING, 15°·경계값 30°는 정상
    issue = check_torso(_torso_person(31.0, 0.0), rep=1)
    assert issue is not None and issue.code == "torso_lean"
    assert issue.severity is Severity.WARNING
    assert issue.threshold == 30.0
    assert check_torso(_torso_person(15.0, 0.0), rep=1) is None
    # 경계는 '초과일 때만 승급'이라 정확히 30°는 정상이다
    assert check_torso(_torso_person(30.0, 0.0), rep=1) is None
    print("✅ 상체−정강이 차이 기반 torso_lean 규칙 동작")


def test_deep_squat_lean_is_not_punished() -> None:
    """깊은 스쿼트의 자연스러운 앞기울임(상체 50°/정강이 35°)은 결함이 아니다.

    절대각 기준(45°)이라면 억울하게 걸렸을 자세. 차이는 15°뿐이므로 정상.
    """
    assert check_torso(_torso_person(50.0, 35.0), rep=1) is None
    # 발목이 뻣뻣해 상체 62°까지 기울어도 정강이가 45°면 균형 잡힌 자세다
    assert check_torso(_torso_person(62.0, 45.0), rep=1) is None
    print("✅ 깊은 스쿼트의 자연스러운 기울임은 처벌하지 않음")


def test_torso_rule_severe_tier() -> None:
    """차이가 40°를 넘으면(굿모닝 자세) ERROR로 올라간다."""
    issue = check_torso(_torso_person(46.0, 5.0), rep=1)  # 차이 41°
    assert issue is not None and issue.code == "excessive_torso_lean"
    assert issue.severity is Severity.ERROR
    # 문구가 WARNING 단계와 달라야 한다 (단계별 특화 안내)
    warn = check_torso(_torso_person(31.0, 0.0), rep=1)
    assert issue.message != warn.message
    print("✅ 굿모닝 자세(excessive_torso_lean) → ERROR + 전용 문구")


def test_torso_hard_cap() -> None:
    """상체 절대 기울기가 70°를 넘으면 정강이와 무관하게 ERROR."""
    # 차이는 30°(WARNING급)지만 상체가 수평에 가까워 절대 상한에 걸린다
    issue = check_torso(_torso_person(75.0, 45.0), rep=1)
    assert issue is not None and issue.code == "excessive_torso_lean"
    assert issue.severity is Severity.ERROR
    print("✅ 절대 상한(70°) 안전장치 동작")


def test_torso_needs_shin_for_relative_tiers() -> None:
    """다리가 안 보이면 상대 판정은 보류하고 절대 상한만 검사한다."""
    assert check_torso(_torso_person(50.0, None), rep=1) is None
    issue = check_torso(_torso_person(75.0, None), rep=1)
    assert issue is not None and issue.code == "excessive_torso_lean"
    print("✅ 정강이 미검출 시 상대 판정 보류 + 절대 상한은 유지")


def test_depth_tiers() -> None:
    """깊이 3단계(좋음/부족/거의 안 앉음)가 각각 다른 코드·등급·문구를 낸다."""
    good = check_depth(85.0, rep=1)
    warn = check_depth(110.0, rep=1)
    error = check_depth(135.0, rep=1)
    assert (good.code, good.severity) == ("good_depth", Severity.GOOD)
    assert (warn.code, warn.severity) == ("shallow_depth", Severity.WARNING)
    assert (error.code, error.severity) == ("very_shallow_depth", Severity.ERROR)
    assert len({good.message, warn.message, error.message}) == 3
    # 경계값은 아래 단계에 속한다 (초과일 때만 다음 단계)
    assert check_depth(90.0, rep=1).code == "good_depth"
    assert check_depth(110.0, rep=1).code == "shallow_depth"
    print("✅ 깊이 3단계 + 단계별 전용 문구")


# --- 통합: 최저점 스냅샷으로 판정하는지 + rep별 종합 판정 ----------------

def test_verdict_correct_on_clean_squat() -> None:
    analyzer = SquatAnalyzer()
    for i, ang in enumerate(CLEAN_REP):
        analyzer.update(_upright_person(ang), i)
    report = analyzer.finalize()
    assert report.rep_count == 1
    assert report.camera_view == "side"
    assert report.rep_verdict(1) is RepVerdict.CORRECT
    print("✅ 깨끗한 스쿼트 → rep 판정 '올바름'")


def test_verdict_uses_bottom_frame() -> None:
    """최저점 부근에만 상체 숙임이 있어도, 서 있는 프레임이 아니라 최저점으로 판정해야 한다."""
    analyzer = SquatAnalyzer()
    for i, ang in enumerate(CLEAN_REP):
        person = _leaning_person(ang) if ang <= 85 else _upright_person(ang)
        analyzer.update(person, i)
    report = analyzer.finalize()
    assert report.rep_count == 1
    codes = {i.code for i in report.issues_for_rep(1)}
    assert "torso_lean" in codes, f"최저점 상체 숙임을 못 잡음: {codes}"
    assert report.rep_verdict(1) is RepVerdict.NEEDS_WORK
    print("✅ 최저점 프레임으로 판정 → '교정 필요'(상체 숙임)")


def test_verdict_incorrect_on_very_shallow_rep() -> None:
    """심각 임계를 넘은 깊이 부족은 rep 판정을 '잘못됨'(incorrect)으로 만든다."""
    analyzer = SquatAnalyzer()
    for i, ang in enumerate(VERY_SHALLOW_REP):
        analyzer.update(_upright_person(ang), i)
    report = analyzer.finalize()
    assert report.rep_count == 1, f"기대 1회, 실제 {report.rep_count}회"
    codes = {i.code for i in report.issues_for_rep(1)}
    assert "very_shallow_depth" in codes, f"심각한 깊이 부족을 못 잡음: {codes}"
    assert report.rep_verdict(1) is RepVerdict.INCORRECT
    print("✅ 거의 앉지 않은 rep → 판정 '잘못됨'")


# --- 리포트 출력(임계값 노출 + rep별 코칭 문구) --------------------------

def test_issue_carries_threshold() -> None:
    """모든 판정 항목이 자신을 발생시킨 기준선을 measured와 같은 단위로 들고 있다."""
    assert check_depth(110.0, rep=1).threshold == 90.0    # shallow_depth
    assert check_depth(135.0, rep=1).threshold == 110.0   # very_shallow_depth
    assert check_depth(85.0, rep=1).threshold == 90.0     # good_depth
    # 상체는 두 갈래: 상대 차이(40°)와 절대 상한(70°)이 서로 다른 기준선이다
    assert check_torso(_torso_person(46.0, 5.0), rep=1).threshold == 40.0
    assert check_torso(_torso_person(75.0, None), rep=1).threshold == 70.0
    assert check_depth(85.0, rep=1).to_dict()["threshold"] == 90.0
    print("✅ Issue.threshold가 지표별 기준선을 정확히 담는다")


def test_boundary_uses_displayed_value() -> None:
    """판정은 반올림된 표시값으로 내린다 → '측정값=기준값인데 결함' 모순이 없다."""
    # 원시 90.04°는 90.0°으로 표시되므로 GOOD, 90.06°은 WARNING이다
    assert check_depth(90.04, rep=1).code == "good_depth"
    assert check_depth(90.06, rep=1).code == "shallow_depth"
    # 원시 110.04°는 110.0°으로 표시되므로 ERROR가 아니라 WARNING이어야 한다
    assert check_depth(110.04, rep=1).code == "shallow_depth"
    assert check_depth(110.06, rep=1).code == "very_shallow_depth"
    # 절대 상한도 같은 규칙: 70.04°는 70.0°으로 표시되므로 결함이 아니다
    assert check_torso(_torso_person(70.04, None), rep=1) is None
    assert check_torso(_torso_person(70.06, None), rep=1) is not None
    # 상대 차이도 마찬가지
    assert check_torso(_torso_person(30.04, 0.0), rep=1) is None
    print("✅ 경계 판정이 표시값 기준으로 일관")


def test_summary_lines_are_actionable_per_rep() -> None:
    """요약이 rep별로 '몇 회차·몇 초 지점·측정값 대 기준값·무엇을 할지'를 낸다."""
    analyzer = SquatAnalyzer(fps=30.0)
    for i, ang in enumerate(CLEAN_REP):
        person = _leaning_person(ang) if ang <= 85 else _upright_person(ang)
        analyzer.update(person, i)
    report = analyzer.finalize()

    lines = report.summary_lines()
    header = next(l for l in lines if "1회차" in l)
    assert "교정 필요" in header
    assert "최저점" in header and "초" in header, f"시각이 없다: {header}"
    detail = next(l for l in lines if l.startswith("   └"))
    assert "가슴을 세운" in detail, f"교정 행동이 없다: {detail}"
    assert "측정" in detail and "기준 30.0°" in detail, f"수치 대비가 없다: {detail}"
    print("✅ rep별 코칭 문구(시각·측정값·기준값·행동) 출력")


def test_summary_omits_timestamp_when_fps_unknown() -> None:
    """fps를 모르면 시각을 지어내지 않고 헤더만 낸다."""
    analyzer = SquatAnalyzer()  # fps 미지정 → *_sec 전부 None
    for i, ang in enumerate(CLEAN_REP):
        analyzer.update(_upright_person(ang), i)
    report = analyzer.finalize()
    header = next(l for l in report.summary_lines() if "1회차" in l)
    assert "최저점" not in header, f"시각을 모르는데 출력했다: {header}"
    print("✅ fps 미상이면 시각 없이 헤더만")


if __name__ == "__main__":
    test_angle_math()
    test_rep_counting()
    test_shallow_rep_counted_with_warning()
    test_torso_rule_relative_to_shin()
    test_deep_squat_lean_is_not_punished()
    test_torso_rule_severe_tier()
    test_torso_hard_cap()
    test_torso_needs_shin_for_relative_tiers()
    test_depth_tiers()
    test_verdict_correct_on_clean_squat()
    test_verdict_uses_bottom_frame()
    test_verdict_incorrect_on_very_shallow_rep()
    test_issue_carries_threshold()
    test_boundary_uses_displayed_value()
    test_summary_lines_are_actionable_per_rep()
    test_summary_omits_timestamp_when_fps_unknown()
    print("\n모든 로직 테스트 통과 🎉")

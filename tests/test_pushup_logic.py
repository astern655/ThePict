"""푸시업 분석 로직 검증 (측면 촬영 전용).

YOLO도 영상도 없이 가짜 관절 좌표로 '팔꿈치각 → 반복 카운트 → 자세 판정'을 확인한다.
실행: python -m tests.test_pushup_logic

푸시업은 몸이 화면상 거의 수평이다. 그래서 좌표를 만들 때
어깨 → 엉덩이 → 발목이 x축을 따라 늘어서게 놓는다(y는 바닥 높이).
"""
from __future__ import annotations

import math

from ai.analysis.exercises.pushup import (
    PushupAnalyzer,
    check_body_line,
    check_depth,
)
from ai.analysis.feedback import RepVerdict, Severity
from ai.pose.keypoints import KP, Keypoint

def _expand(sequence: list[float], times: int = 3) -> list[float]:
    """각 단계를 여러 프레임으로 늘려 실제 영상의 시간 해상도에 맞춘다.

    실영상에서 푸시업 1회는 25~30fps로 40~60프레임에 걸쳐 일어난다. 한 단계를
    1프레임으로 적으면 중앙값 필터(윈도 7)가 동작 자체를 지워 버려, 필터를
    끄지 않고는 테스트가 성립하지 않는다. 그건 테스트가 비현실적인 것이다.
    """
    return [value for value in sequence for _ in range(times)]


# 정상 푸시업 1회: 팔 펴짐 → 내려감 → 최저점(80도) 유지 → 다시 펴짐.
CLEAN_REP = _expand(
    [175, 175, 165, 150, 130, 110, 95, 85, 80, 80, 85, 95, 115, 135, 155, 170, 175, 175])
# 얕은 푸시업 1회: 최저점 100도 (rep으로는 세되 깊이 부족 WARNING)
SHALLOW_REP = _expand([175, 175, 165, 150, 135, 120, 100, 100, 120, 140, 160, 175, 175])
# 거의 안 내려간 1회: 최저점 125도로 심각 임계(110도)를 넘어 ERROR
VERY_SHALLOW_REP = _expand([175, 175, 165, 150, 135, 125, 125, 135, 150, 165, 175, 175])

_SHOULDER = (200.0, 300.0)   # 화면 왼쪽이 머리, 오른쪽이 발
_HIP_X = 400.0
_ANKLE = (600.0, 300.0)


def _blank() -> list[Keypoint]:
    return [Keypoint(0.0, 0.0, 0.0) for _ in range(17)]


def _set(kp: list[Keypoint], **points: tuple[float, float]) -> list[Keypoint]:
    for name, (x, y) in points.items():
        kp[getattr(KP, name)] = Keypoint(x, y, 0.9)
    return kp


def _wrist_for_elbow_angle(angle_deg: float) -> tuple[float, float]:
    """팔꿈치각이 angle_deg가 되도록 손목 위치를 만든다.

    팔꿈치는 어깨 바로 아래(바닥 쪽)에 두고, 어깨→팔꿈치 방향을 angle_deg 회전해
    팔꿈치→손목 방향으로 삼는다. 그러면 angle_at(어깨, 팔꿈치, 손목) == angle_deg.
    """
    elbow = (_SHOULDER[0], _SHOULDER[1] + 80.0)
    ux, uy = 0.0, 1.0  # 어깨 → 팔꿈치 = 아래쪽
    th = math.radians(angle_deg)
    # 팔꿈치→어깨 방향을 angle_deg 회전 → 팔꿈치→손목 방향
    bx, by = -ux, -uy
    wx = elbow[0] + (bx * math.cos(th) - by * math.sin(th)) * 80.0
    wy = elbow[1] + (bx * math.sin(th) + by * math.cos(th)) * 80.0
    return (wx, wy)


def _pushup_person(elbow_angle_deg: float, hip_offset: float = 0.0) -> list[Keypoint]:
    """푸시업 자세. 팔꿈치각과 엉덩이의 수직 오프셋(px)을 지정한다.

    hip_offset > 0 이면 엉덩이가 화면 아래(처짐), < 0 이면 위(솟음).
    어깨·발목이 같은 높이라 offset이 0이면 몸통 이탈각도 0이다.
    """
    elbow = (_SHOULDER[0], _SHOULDER[1] + 80.0)
    wrist = _wrist_for_elbow_angle(elbow_angle_deg)
    return _set(
        _blank(),
        LEFT_SHOULDER=_SHOULDER, LEFT_ELBOW=elbow, LEFT_WRIST=wrist,
        LEFT_HIP=(_HIP_X, _SHOULDER[1] + hip_offset),
        LEFT_ANKLE=_ANKLE,
    )


def _hip_offset_for_deviation(deviation_deg: float) -> float:
    """몸통 이탈각이 deviation_deg가 되는 엉덩이 오프셋(px).

    어깨-엉덩이, 엉덩이-발목 두 선분이 각각 200px 수평이고 엉덩이가 d만큼
    내려가면 이탈각 = 2 * atan(d / 200).
    """
    return 200.0 * math.tan(math.radians(deviation_deg) / 2)


# --- 반복 카운트 --------------------------------------------------------

def test_rep_counting() -> None:
    analyzer = PushupAnalyzer()
    for i, ang in enumerate(CLEAN_REP * 3):
        analyzer.update(_pushup_person(ang), i)
    report = analyzer.finalize()
    assert report.rep_count == 3, f"기대 3회, 실제 {report.rep_count}회"
    assert report.partial_rep_count == 0
    assert report.exercise == "푸시업"
    print(f"✅ 푸시업 반복 카운트 정확: {report.rep_count}회")


def test_shallow_dip_is_counted_but_flagged() -> None:
    """최저 140°까지만 내려간 반복은 세되 '거의 안 내려감' ERROR를 붙인다.

    반복 카운트 기준은 영상별로 보정되므로(§적응 임계), '이 사람이 이 영상에서
    한 동작' 안에서는 이것도 한 번의 오르내림이다. 대신 깊이 판정은 절대 기준
    (90°/110°)이라 140°는 very_shallow_depth로 걸린다. 조용히 0회로 세는 것보다
    "1회 했는데 너무 얕다"고 말해 주는 편이 사용자에게 유용하다.
    """
    dip = _expand([175, 175, 165, 155, 140, 140, 155, 170, 175])  # 최저 140°
    analyzer = PushupAnalyzer()
    for i, ang in enumerate(dip):
        analyzer.update(_pushup_person(ang), i)
    report = analyzer.finalize()
    assert report.rep_count == 1, f"기대 1회, 실제 {report.rep_count}회"
    codes = {i.code for i in report.issues_for_rep(1)}
    assert "very_shallow_depth" in codes, codes
    assert report.rep_verdict(1) is RepVerdict.INCORRECT
    print("✅ 얕은 반복은 세되 깊이 ERROR로 표시")


def test_tiny_wobble_does_not_become_reps() -> None:
    """각도 변화 폭이 좁으면(반복 동작이 아니면) 적응 임계를 끄고 세지 않는다.

    영상별 보정의 위험은 '아무 동작도 없는 영상의 잔떨림'을 그 영상의 전체
    범위로 착각해 rep으로 세는 것이다. 폭 기준(PUSHUP_ADAPTIVE_MIN_SPAN)이 이를 막는다.
    """
    wobble = _expand([175, 172, 168, 170, 174, 167, 171, 175, 173])  # 폭 8°
    analyzer = PushupAnalyzer()
    for i, ang in enumerate(wobble):
        analyzer.update(_pushup_person(ang), i)
    report = analyzer.finalize()
    assert report.rep_count == 0, f"잔떨림을 {report.rep_count}회로 셌다"
    print("✅ 폭이 좁은 영상은 보정하지 않아 잔떨림을 세지 않음")


def test_smoothing_rejects_spike() -> None:
    """최저점 한가운데 관절 오검출로 각도가 한 프레임 튀어도 rep이 두 번 세지지 않는다."""
    spiky = list(CLEAN_REP)
    spiky[9] = 175  # 최저점(80도) 한 프레임이 175도로 튐 (관절 오검출 시뮬레이션)
    analyzer = PushupAnalyzer()
    for i, ang in enumerate(spiky):
        analyzer.update(_pushup_person(ang), i)
    report = analyzer.finalize()
    assert report.rep_count == 1, f"스파이크로 rep이 잘못 세짐: {report.rep_count}회"
    codes = {i.code for i in report.issues_for_rep(1)}
    assert "shallow_depth" not in codes, "스파이크가 최저점 판정을 흐림"
    print("✅ 중앙값 필터가 단일 프레임 스파이크를 제거")


def test_locked_arm_wobble_is_not_partial() -> None:
    """팔을 편 채로 흔들리는 정도(155~175도)는 부분 반복으로 치지 않는다."""
    analyzer = PushupAnalyzer()
    for i, ang in enumerate(_expand([175, 168, 158, 165, 172, 156, 163, 175, 175])):
        analyzer.update(_pushup_person(ang), i)
    report = analyzer.finalize()
    assert report.rep_count == 0
    assert report.partial_rep_count == 0
    print("✅ 팔 편 상태의 잔떨림은 부분 반복 아님")


def test_rep_record_timestamps() -> None:
    """rep별 시작·최저점·종료 프레임/시각이 기록된다(UI 시킹용)."""
    analyzer = PushupAnalyzer(fps=30.0)
    for i, ang in enumerate(CLEAN_REP):
        analyzer.update(_pushup_person(ang), i)
    report = analyzer.finalize()
    record = report.rep_record(1)
    assert record is not None
    assert record.start_frame < record.bottom_frame < record.end_frame
    assert record.duration_sec is not None and record.duration_sec > 0
    assert record.bottom_angle is not None and record.bottom_angle <= 90.0
    assert report.rep_verdicts()[0]["bottom_sec"] == record.bottom_sec
    print("✅ 푸시업 rep 타임스탬프 기록")


# --- 측면 촬영 자동 검증 -------------------------------------------------

def _front_view_person() -> list[Keypoint]:
    """머리쪽/발쪽에서 찍은 것처럼 양 어깨가 넓게 벌어져 보이는 사람.

    비율(어깨 간격 ÷ 몸통 길이) ≈ 2.0 — 실측한 정면 푸시업의 상단(1.78~3.03)에
    해당한다. 푸시업은 측면 영상도 비율이 1.08까지 올라가서(config 주석 참고)
    이 정도로 명백해야 정면으로 판정한다.
    """
    return _set(
        _blank(),
        LEFT_SHOULDER=(200.0, 100.0), RIGHT_SHOULDER=(400.0, 100.0),
        LEFT_HIP=(265.0, 200.0), RIGHT_HIP=(335.0, 200.0),
    )


def test_front_view_rejected() -> None:
    analyzer = PushupAnalyzer()
    for i in range(12):
        analyzer.update(_front_view_person(), i)
    report = analyzer.finalize()
    codes = {i.code for i in report.video_issues}
    assert "not_side_view" in codes, f"정면 영상을 못 잡음: {codes}"
    print("✅ 정면(머리쪽) 영상 자동 검출 → 재촬영 안내")


def test_side_view_passes() -> None:
    analyzer = PushupAnalyzer()
    for i, ang in enumerate(CLEAN_REP):
        analyzer.update(_pushup_person(ang), i)
    report = analyzer.finalize()
    assert "not_side_view" not in {i.code for i in report.video_issues}
    print("✅ 측면 영상은 경고 없음")


# --- 자세 규칙(순수 함수) -----------------------------------------------

def test_depth_tiers() -> None:
    good = check_depth(85.0, rep=1)
    warn = check_depth(100.0, rep=1)
    error = check_depth(125.0, rep=1)
    assert (good.code, good.severity) == ("good_depth", Severity.GOOD)
    assert (warn.code, warn.severity) == ("shallow_depth", Severity.WARNING)
    assert (error.code, error.severity) == ("very_shallow_depth", Severity.ERROR)
    assert len({good.message, warn.message, error.message}) == 3
    # 경계값은 아래 단계에 속한다(초과일 때만 승급)
    assert check_depth(90.0, rep=1).code == "good_depth"
    assert check_depth(110.0, rep=1).code == "shallow_depth"
    print("✅ 푸시업 깊이 3단계 + 단계별 전용 문구")


def test_body_line_straight_is_clean() -> None:
    """어깨-엉덩이-발목이 일직선이면 결함이 아니다."""
    assert check_body_line(_pushup_person(80.0), rep=1) is None
    # 경계(15°)도 '초과'가 아니라 정상이다
    boundary = _hip_offset_for_deviation(15.0)
    assert check_body_line(_pushup_person(80.0, boundary), rep=1) is None
    print("✅ 일직선 몸통은 통과, 경계값도 정상")


def test_hip_sag_and_pike_get_opposite_coaching() -> None:
    """엉덩이 처짐과 솟음은 교정 방법이 반대라 문구가 달라야 한다."""
    offset = _hip_offset_for_deviation(20.0)
    sag = check_body_line(_pushup_person(80.0, offset), rep=1)
    pike = check_body_line(_pushup_person(80.0, -offset), rep=1)

    assert sag is not None and sag.code == "body_line_break"
    assert pike is not None and pike.code == "body_line_break"
    assert sag.severity is Severity.WARNING and pike.severity is Severity.WARNING
    assert "처졌" in sag.message, sag.message
    assert "솟았" in pike.message, pike.message
    # 같은 크기로 벗어났으므로 측정값은 같아야 한다(방향만 다르다)
    assert sag.measured == pike.measured
    print("✅ 처짐/솟음을 방향별로 갈라 안내")


def test_body_line_severe_tier() -> None:
    """이탈각이 25°를 넘으면 ERROR로 올라간다."""
    issue = check_body_line(_pushup_person(80.0, _hip_offset_for_deviation(30.0)), rep=1)
    assert issue is not None and issue.code == "excessive_body_line_break"
    assert issue.severity is Severity.ERROR
    assert issue.threshold == 25.0
    print("✅ 심각한 몸통 꺾임 → ERROR")


def test_body_line_falls_back_to_knee() -> None:
    """발목이 안 보이면 무릎까지로 몸통 선을 잰다(무릎 대고 하는 푸시업)."""
    person = _pushup_person(80.0, _hip_offset_for_deviation(30.0))
    person[KP.LEFT_ANKLE] = Keypoint(*_ANKLE, 0.1)      # 발목 신뢰도 미달
    person[KP.LEFT_KNEE] = Keypoint(*_ANKLE, 0.9)       # 대신 무릎이 보인다
    issue = check_body_line(person, rep=1)
    assert issue is not None and issue.severity is Severity.ERROR
    print("✅ 발목 미검출 시 무릎으로 대체 측정")


def test_body_line_skipped_when_hip_hidden() -> None:
    """엉덩이가 안 보이면 판정을 보류한다(지어내지 않는다)."""
    person = _pushup_person(80.0, _hip_offset_for_deviation(30.0))
    person[KP.LEFT_HIP] = Keypoint(_HIP_X, 300.0, 0.2)
    assert check_body_line(person, rep=1) is None
    print("✅ 엉덩이 미검출 시 몸통 판정 보류")


# --- 통합: 최저점 스냅샷 판정 + rep 종합 판정 ---------------------------

def test_verdict_correct_on_clean_pushup() -> None:
    analyzer = PushupAnalyzer(fps=30.0)
    for i, ang in enumerate(CLEAN_REP):
        analyzer.update(_pushup_person(ang), i)
    report = analyzer.finalize()
    assert report.rep_count == 1
    assert report.rep_verdict(1) is RepVerdict.CORRECT
    print("✅ 깨끗한 푸시업 → rep 판정 '올바름'")


def test_verdict_needs_work_on_shallow_pushup() -> None:
    analyzer = PushupAnalyzer(fps=30.0)
    for i, ang in enumerate(SHALLOW_REP):
        analyzer.update(_pushup_person(ang), i)
    report = analyzer.finalize()
    assert report.rep_count == 1
    codes = {i.code for i in report.issues_for_rep(1)}
    assert "shallow_depth" in codes, codes
    assert report.rep_verdict(1) is RepVerdict.NEEDS_WORK
    print("✅ 얕은 푸시업 → '교정 필요'")


def test_verdict_incorrect_on_very_shallow_pushup() -> None:
    analyzer = PushupAnalyzer(fps=30.0)
    for i, ang in enumerate(VERY_SHALLOW_REP):
        analyzer.update(_pushup_person(ang), i)
    report = analyzer.finalize()
    assert report.rep_count == 1
    assert report.rep_verdict(1) is RepVerdict.INCORRECT
    print("✅ 거의 안 내려간 푸시업 → '잘못됨'")


def test_verdict_uses_bottom_frame() -> None:
    """최저점 부근에만 엉덩이가 처져도 그 프레임으로 판정해야 한다."""
    offset = _hip_offset_for_deviation(20.0)
    analyzer = PushupAnalyzer(fps=30.0)
    for i, ang in enumerate(CLEAN_REP):
        analyzer.update(_pushup_person(ang, offset if ang <= 95 else 0.0), i)
    report = analyzer.finalize()
    codes = {i.code for i in report.issues_for_rep(1)}
    assert "body_line_break" in codes, f"최저점 처짐을 못 잡음: {codes}"
    assert report.rep_verdict(1) is RepVerdict.NEEDS_WORK
    print("✅ 최저점 프레임으로 몸통 판정")


def test_bottom_measurement_recorded_even_when_correct() -> None:
    """결함이 아니어도 몸통 이탈각이 rep 기록에 남아야 한다(임계값 재검증용)."""
    offset = _hip_offset_for_deviation(10.0)  # 10° → 결함 아님
    analyzer = PushupAnalyzer(fps=30.0)
    for i, ang in enumerate(CLEAN_REP):
        analyzer.update(_pushup_person(ang, offset), i)
    report = analyzer.finalize()

    assert report.rep_verdict(1) is RepVerdict.CORRECT
    record = report.rep_record(1)
    assert record.bottom_body_line_dev is not None
    assert abs(record.bottom_body_line_dev - 10.0) < 0.2, record.bottom_body_line_dev
    assert record.to_dict()["bottom_body_line_dev"] == record.bottom_body_line_dev
    print("✅ 정상 rep에서도 몸통 이탈각이 기록됨")


def test_ended_mid_rep_is_reported() -> None:
    """내려간 상태로 영상이 끝나면 마지막 1회가 빠졌음을 알린다."""
    analyzer = PushupAnalyzer(fps=30.0)
    for i, ang in enumerate(_expand([175, 175, 160, 140, 120, 90, 90])):
        analyzer.update(_pushup_person(ang), i)
    report = analyzer.finalize()
    assert report.rep_count == 0
    codes = {i.code for i in report.video_issues}
    assert "ended_mid_rep" in codes, codes
    print("✅ 내려간 자세로 끝난 영상 안내")


def test_registry_exposes_pushup() -> None:
    from ai.analysis.exercises import available_exercises, create_analyzer
    assert "pushup" in available_exercises()
    assert isinstance(create_analyzer("pushup", fps=30.0), PushupAnalyzer)
    print("✅ 레지스트리에 pushup 등록됨")


if __name__ == "__main__":
    test_rep_counting()
    test_shallow_dip_is_counted_but_flagged()
    test_tiny_wobble_does_not_become_reps()
    test_smoothing_rejects_spike()
    test_locked_arm_wobble_is_not_partial()
    test_rep_record_timestamps()
    test_front_view_rejected()
    test_side_view_passes()
    test_depth_tiers()
    test_body_line_straight_is_clean()
    test_hip_sag_and_pike_get_opposite_coaching()
    test_body_line_severe_tier()
    test_body_line_falls_back_to_knee()
    test_body_line_skipped_when_hip_hidden()
    test_verdict_correct_on_clean_pushup()
    test_verdict_needs_work_on_shallow_pushup()
    test_verdict_incorrect_on_very_shallow_pushup()
    test_verdict_uses_bottom_frame()
    test_bottom_measurement_recorded_even_when_correct()
    test_ended_mid_rep_is_reported()
    test_registry_exposes_pushup()
    print("\n푸시업 로직 테스트 통과 🎉")

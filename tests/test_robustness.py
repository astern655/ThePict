"""입력 이상(디코딩 중단·추론 실패·프레임 유실)에 대한 방어 검증.

실행: python -m tests.test_robustness  (또는 pytest)

여기서 확인하는 것은 "정확한 값이 나오는가"가 아니라 "틀린 값을 조용히
내지 않는가"다. 분석이 영상 전체를 못 봤으면 그 사실이 리포트에 남아야 한다.
"""
from __future__ import annotations

from ai.analysis.exercises.pushup import PushupAnalyzer
from ai.analysis.exercises.squat import SquatAnalyzer
from ai.analysis.feedback import Report
from ai.engine import _decode_gate, _inference_gate
from ai.pose.keypoints import KP, Keypoint
from tests.test_pushup_logic import CLEAN_REP as PUSHUP_CLEAN_REP
from tests.test_pushup_logic import _hip_offset_for_deviation, _pushup_person
from tests.test_squat_logic import CLEAN_REP, _upright_person


# --- (a) 디코딩 중단 감지 ------------------------------------------------

def test_truncated_video_is_reported() -> None:
    """선언된 프레임 수의 절반만 읽고 끝났으면 조기 종료로 안내한다."""
    report = Report(exercise="스쿼트")
    _decode_gate(report, read_frames=150, declared_frames=300)
    codes = {i.code for i in report.video_issues}
    assert codes == {"truncated_video"}, f"조기 종료 미안내: {codes}"
    print("✅ 손상 영상 조기 종료 → truncated_video 안내")


def test_full_read_is_silent() -> None:
    """끝까지 읽었으면 경고가 붙지 않는다."""
    report = Report(exercise="스쿼트")
    _decode_gate(report, read_frames=300, declared_frames=300)
    assert not report.video_issues
    print("✅ 정상 완독 시 경고 없음")


def test_unknown_frame_count_is_skipped() -> None:
    """총 프레임 수를 모르는 영상(스트림 등)은 비교 자체가 불가능해 판단을 보류한다."""
    report = Report(exercise="스쿼트")
    _decode_gate(report, read_frames=10, declared_frames=0)
    assert not report.video_issues
    print("✅ 프레임 수 미상 영상은 조기 종료 판정 보류")


# --- (b) 추론 실패 격리 --------------------------------------------------

def test_inference_failures_reported() -> None:
    report = Report(exercise="스쿼트")
    _inference_gate(report, processed=100, failed=10)
    assert {i.code for i in report.video_issues} == {"inference_error"}
    print("✅ 추론 실패 프레임이 많으면 inference_error 안내")


def test_rare_inference_failure_is_silent() -> None:
    """1% 수준의 산발적 실패는 유실 처리로 흡수되므로 경고하지 않는다."""
    report = Report(exercise="스쿼트")
    _inference_gate(report, processed=100, failed=1)
    assert not report.video_issues
    print("✅ 산발적 추론 실패는 경고 없음")


# --- (c) 프레임 유실 구간 ------------------------------------------------

def test_short_gap_is_tolerated() -> None:
    """짧은 유실(임계 이내)은 그대로 이어붙여 rep을 정상 카운트한다."""
    analyzer = SquatAnalyzer(fps=30.0)  # 임계 = 0.5초 * 30 = 15프레임
    frame = 0
    for idx, ang in enumerate(CLEAN_REP):
        analyzer.update(_upright_person(ang), frame)
        # 최저점 근처에서 5프레임 유실 (임계 15프레임 이내)
        frame += 6 if idx == 6 else 1
    report = analyzer.finalize()
    assert report.rep_count == 1, f"짧은 유실에 rep을 놓침: {report.rep_count}"
    assert report.tracking_gap_count == 0
    assert not any(i.code == "tracking_gap" for i in report.video_issues)
    print("✅ 짧은 유실은 그대로 이어붙여 정상 카운트")


def test_long_gap_drops_in_progress_rep() -> None:
    """앉아 있는 도중 긴 유실이 나면 그 rep은 폐기하고 사실을 남긴다."""
    analyzer = SquatAnalyzer(fps=30.0)
    frame = 0
    for idx, ang in enumerate(CLEAN_REP):
        analyzer.update(_upright_person(ang), frame)
        # 최저점(80도) 직후 60프레임(2초) 유실
        frame += 60 if idx == 7 else 1
    report = analyzer.finalize()
    assert report.tracking_gap_count == 1, f"끊김 미감지: {report.tracking_gap_count}"
    assert report.dropped_rep_count == 1, f"진행 중 rep 미폐기: {report.dropped_rep_count}"
    assert report.rep_count == 0, f"반쯤만 본 rep을 세었다: {report.rep_count}"
    codes = {i.code for i in report.video_issues}
    assert "tracking_gap" in codes, f"끊김 미안내: {codes}"
    # 폐기된 rep에는 깊이 판정이 붙지 않아야 한다(잰 적 없는 값을 지어내지 않기).
    assert not report.issues, f"폐기 rep에 판정이 남음: {report.issues}"
    print("✅ 긴 유실 구간의 진행 중 rep은 폐기 + tracking_gap 안내")


def test_gap_while_standing_keeps_counting() -> None:
    """서 있는 동안의 긴 유실은 rep을 버리지 않고, 이후 동작을 정상 카운트한다."""
    analyzer = SquatAnalyzer(fps=30.0)
    frame = 0
    # 선 채로 시작 → 긴 유실 → 온전한 rep 1회
    for ang in [175.0, 175.0]:
        analyzer.update(_upright_person(ang), frame)
        frame += 1
    frame += 90  # 3초 유실 (서 있는 동안)
    for ang in CLEAN_REP:
        analyzer.update(_upright_person(ang), frame)
        frame += 1
    report = analyzer.finalize()
    assert report.tracking_gap_count == 1
    assert report.dropped_rep_count == 0, "선 채로 난 끊김인데 rep을 버렸다"
    assert report.rep_count == 1, f"유실 이후 rep을 못 셈: {report.rep_count}"
    print("✅ 서 있는 동안의 유실은 rep 손실 없이 복구")


def test_gap_does_not_mix_smoother_samples() -> None:
    """유실 직후 첫 프레임은 유실 이전 값과 섞이지 않는다(필터 리셋)."""
    analyzer = SquatAnalyzer(fps=30.0)
    for i, ang in enumerate([175.0, 175.0, 175.0]):
        analyzer.update(_upright_person(ang), i)
    analyzer.update(_upright_person(90.0), 200)  # 긴 유실 후 앉은 자세
    # 필터가 리셋됐다면 90도가 그대로 통과한다(리셋 전이면 175도가 중앙값).
    assert analyzer._last_angle is not None
    assert abs(analyzer._last_angle - 90.0) < 1.0, (
        f"유실 전후 값이 필터에서 섞임: {analyzer._last_angle}"
    )
    print("✅ 유실 구간에서 중앙값 필터 리셋")


# --- (d) NaN 각도 -------------------------------------------------------

def test_nan_angle_does_not_stall_state_machine() -> None:
    """관절 좌표가 완전히 겹쳐 각도가 NaN이 되어도 분석이 멈추지 않는다.

    NaN은 모든 비교가 False라, 상태기계에 흘려보내면 그 뒤로 rep이 영영 세어지지
    않는다(조용한 정지). 못 잰 프레임과 똑같이 걸러야 한다.
    """
    degenerate = _upright_person(120.0)
    hip = degenerate[KP.LEFT_HIP]
    # 엉덩이·무릎·발목을 한 점에 겹친다 → angle_at이 NaN
    for idx in (KP.LEFT_KNEE, KP.LEFT_ANKLE):
        degenerate[idx] = Keypoint(hip.x, hip.y, 0.9)

    analyzer = SquatAnalyzer(fps=30.0)
    frame = 0
    for _ in range(3):  # 정상 rep 앞에 NaN 프레임을 먼저 흘린다
        analyzer.update(degenerate, frame)
        frame += 1
    for ang in CLEAN_REP:
        analyzer.update(_upright_person(ang), frame)
        frame += 1

    report = analyzer.finalize()
    assert report.rep_count == 1, f"NaN 이후 카운트가 멈춤: {report.rep_count}"
    assert report.rep_record(1).bottom_angle is not None
    print("✅ NaN 각도를 '못 잼'으로 처리 → 상태기계 정지 없음")


def test_nan_angle_is_not_recorded_as_measurement() -> None:
    """NaN이 측정값으로 기록되지도 않는다(지어낸 값 금지)."""
    from ai.analysis.exercises.squat import _mid_knee_angle, _torso_lean

    person = _upright_person(100.0)
    hip = person[KP.LEFT_HIP]
    for idx in (KP.LEFT_KNEE, KP.LEFT_ANKLE, KP.LEFT_SHOULDER):
        person[idx] = Keypoint(hip.x, hip.y, 0.9)
    assert _mid_knee_angle(person) is None
    assert _torso_lean(person) is None
    print("✅ 겹친 좌표에서 각도를 지어내지 않음")


# --- (e) 푸시업 경로 ------------------------------------------------------
# 유실 처리 기계는 base.AngleRepAnalyzer 한 벌뿐이라 위 스쿼트 테스트가 기계를
# 검증한다. 여기서는 **푸시업 고유 조건**에서도 같은 보증이 유지되는지 본다:
# 기준 관절이 팔꿈치이고, 몸통 판정이 발목→무릎으로 대체될 수 있다는 점.

def test_pushup_long_gap_drops_in_progress_rep() -> None:
    """내려간 도중 긴 유실이 나면 푸시업도 그 rep을 폐기한다."""
    analyzer = PushupAnalyzer(fps=30.0)
    frame = 0
    bottom_idx = PUSHUP_CLEAN_REP.index(min(PUSHUP_CLEAN_REP))
    for idx, ang in enumerate(PUSHUP_CLEAN_REP):
        analyzer.update(_pushup_person(ang), frame)
        frame += 60 if idx == bottom_idx else 1  # 최저점 직후 2초 유실
    report = analyzer.finalize()
    assert report.tracking_gap_count == 1
    assert report.dropped_rep_count == 1
    assert report.rep_count == 0, f"반쯤만 본 rep을 세었다: {report.rep_count}"
    assert not report.issues, f"폐기 rep에 판정이 남음: {report.issues}"
    print("✅ 푸시업도 유실 구간의 진행 중 rep을 폐기")


def test_pushup_gap_requires_full_extension_before_counting() -> None:
    """끊김 이후에는 팔을 완전히 편 자세를 다시 봐야 카운트를 재개한다.

    스쿼트의 '완전히 선 자세'에 해당한다. 내려간 중간부터 이어 세면 내려가는
    구간을 못 본 rep을 세게 된다.
    """
    analyzer = PushupAnalyzer(fps=30.0)
    frame = 0
    for ang in PUSHUP_CLEAN_REP[:6]:          # 내려가는 중까지만
        analyzer.update(_pushup_person(ang), frame)
        frame += 1
    frame += 90                                # 3초 유실
    for ang in [90, 90, 175, 175]:             # 유실 이후 바로 올라옴
        analyzer.update(_pushup_person(ang), frame)
        frame += 1
    report = analyzer.finalize()
    assert report.rep_count == 0, f"내려가는 구간을 못 본 rep을 셌다: {report.rep_count}"
    print("✅ 끊김 이후 완전히 편 자세를 볼 때까지 카운트 보류")


def test_pushup_hidden_ankle_does_not_fabricate_body_line() -> None:
    """발목이 사라져도 무릎으로 대체해 재고, 둘 다 없으면 판정을 보류한다.

    푸시업은 발이 프레임을 벗어나기 쉬워서, 이 대체가 조용히 틀린 값을 내면
    안 된다. 무릎도 없으면 rep은 세되 몸통 결함은 붙이지 않는다.
    """
    offset = _hip_offset_for_deviation(30.0)  # ERROR급으로 꺾인 몸통

    with_knee = PushupAnalyzer(fps=30.0)
    without_legs = PushupAnalyzer(fps=30.0)
    for i, ang in enumerate(PUSHUP_CLEAN_REP):
        person = _pushup_person(ang, offset)
        person[KP.LEFT_ANKLE] = Keypoint(person[KP.LEFT_ANKLE].x, person[KP.LEFT_ANKLE].y, 0.1)

        knee_visible = [Keypoint(kp.x, kp.y, kp.confidence) for kp in person]
        knee_visible[KP.LEFT_KNEE] = Keypoint(600.0, 300.0, 0.9)  # 무릎은 보인다
        with_knee.update(knee_visible, i)
        without_legs.update(person, i)  # 발목·무릎 둘 다 없음

    knee_report = with_knee.finalize()
    legless_report = without_legs.finalize()

    knee_codes = {i.code for i in knee_report.issues_for_rep(1)}
    assert "excessive_body_line_break" in knee_codes, f"무릎 대체 실패: {knee_codes}"

    assert legless_report.rep_count == 1, "팔꿈치는 보이는데 rep을 놓쳤다"
    legless_codes = {i.code for i in legless_report.issues_for_rep(1)}
    assert not (legless_codes - {"good_depth"}), f"못 잰 몸통을 판정했다: {legless_codes}"
    assert legless_report.rep_record(1).bottom_body_line_dev is None
    print("✅ 발목 유실 시 무릎으로 대체, 다리가 다 없으면 판정 보류")


if __name__ == "__main__":
    test_truncated_video_is_reported()
    test_full_read_is_silent()
    test_unknown_frame_count_is_skipped()
    test_inference_failures_reported()
    test_rare_inference_failure_is_silent()
    test_short_gap_is_tolerated()
    test_long_gap_drops_in_progress_rep()
    test_gap_while_standing_keeps_counting()
    test_gap_does_not_mix_smoother_samples()
    test_nan_angle_does_not_stall_state_machine()
    test_nan_angle_is_not_recorded_as_measurement()
    test_pushup_long_gap_drops_in_progress_rep()
    test_pushup_gap_requires_full_extension_before_counting()
    test_pushup_hidden_ankle_does_not_fabricate_body_line()
    print("\n전체 통과")

"""신규 기능 검증: 평활화·부분 반복·rep 타임스탬프·측면 검증·검출률 게이트.

실행: python -m tests.test_squat_extended  (또는 pytest)
"""
from __future__ import annotations

from ai.analysis.exercises.squat import SquatAnalyzer
from ai.analysis.feedback import Report
from ai.engine import _detection_gate
from tests.test_squat_logic import CLEAN_REP, _blank, _set, _upright_person


# --- 평활화(중앙값 필터) -------------------------------------------------

def test_smoothing_rejects_spike() -> None:
    """최저점 한가운데 관절 오검출로 각도가 한 프레임 튀어도 rep이 두 번 세지지 않는다."""
    spiky = list(CLEAN_REP)
    spiky[8] = 175.0  # 최저점(80도) 한 프레임이 175도로 튐 (관절 오검출 시뮬레이션)
    analyzer = SquatAnalyzer()
    for i, ang in enumerate(spiky):
        analyzer.update(_upright_person(ang), i)
    report = analyzer.finalize()
    assert report.rep_count == 1, f"스파이크로 rep이 잘못 세짐: {report.rep_count}회"
    codes = {i.code for i in report.issues_for_rep(1)}
    assert "shallow_depth" not in codes, "스파이크가 최저점 판정을 흐림"
    print("✅ 중앙값 필터가 단일 프레임 스파이크를 제거 (rep 이중 카운트 방지)")


# --- 부분 반복 -----------------------------------------------------------

def test_partial_rep_detected() -> None:
    """DOWN 임계(140)까지 못 간 얕은 내려감은 rep이 아니라 부분 반복으로 집계."""
    sequence = [170, 170, 160, 155, 150, 145, 145, 150, 155, 160, 170, 175, 175]
    analyzer = SquatAnalyzer()
    for i, ang in enumerate(sequence):
        analyzer.update(_upright_person(ang), i)
    report = analyzer.finalize()
    assert report.rep_count == 0
    assert report.partial_rep_count == 1, f"부분 반복 미검출: {report.partial_rep_count}"
    codes = {i.code for i in report.video_issues}
    assert "partial_reps" in codes
    print("✅ 부분 반복 검출 + 영상 수준 안내")


def test_standing_wobble_is_not_partial() -> None:
    """서 있을 때의 잔떨림(155~175도)은 부분 반복으로 치지 않는다."""
    sequence = [170, 165, 158, 162, 170, 156, 163, 175, 170]
    analyzer = SquatAnalyzer()
    for i, ang in enumerate(sequence):
        analyzer.update(_upright_person(ang), i)
    report = analyzer.finalize()
    assert report.rep_count == 0
    assert report.partial_rep_count == 0
    print("✅ 서 있는 잔떨림은 부분 반복 아님")


# --- rep 타임스탬프 ------------------------------------------------------

def test_rep_record_timestamps() -> None:
    """rep별 시작·최저점·종료 프레임/시각이 기록된다."""
    analyzer = SquatAnalyzer(fps=30.0)
    for i, ang in enumerate(CLEAN_REP):
        analyzer.update(_upright_person(ang), i)
    report = analyzer.finalize()
    record = report.rep_record(1)
    assert record is not None
    assert record.start_frame < record.bottom_frame < record.end_frame
    assert record.start_sec is not None and record.end_sec is not None
    assert record.duration_sec is not None and record.duration_sec > 0
    assert record.bottom_angle is not None and record.bottom_angle <= 100.0
    # to_dict/rep_verdicts에도 시각이 실린다 (UI 시킹용)
    verdicts = report.rep_verdicts()
    assert verdicts[0]["bottom_sec"] == record.bottom_sec
    print("✅ rep별 타임스탬프 기록 (UI 시킹용)")


def test_rep_record_without_fps() -> None:
    """fps를 모르면 프레임 번호만 기록하고 시각(초)은 None."""
    analyzer = SquatAnalyzer()
    for i, ang in enumerate(CLEAN_REP):
        analyzer.update(_upright_person(ang), i)
    report = analyzer.finalize()
    record = report.rep_record(1)
    assert record is not None
    assert record.start_sec is None and record.duration_sec is None
    print("✅ fps 없으면 시각(초) 기록 생략")


# --- 측면 촬영 자동 검증 -------------------------------------------------

def _front_view_person() -> list:
    """정면 촬영처럼 양 어깨가 넓게 벌어져 보이는 사람."""
    return _set(
        _blank(),
        LEFT_SHOULDER=(250.0, 100.0), RIGHT_SHOULDER=(350.0, 100.0),
        LEFT_HIP=(265.0, 250.0), RIGHT_HIP=(335.0, 250.0),
    )


def test_front_view_rejected() -> None:
    analyzer = SquatAnalyzer()
    for i in range(12):
        analyzer.update(_front_view_person(), i)
    report = analyzer.finalize()
    codes = {i.code for i in report.video_issues}
    assert "not_side_view" in codes, f"정면 영상을 못 잡음: {codes}"
    print("✅ 정면 영상 자동 검출 → 재촬영 안내")


def test_side_view_passes() -> None:
    """측면 시퀀스(한쪽 어깨만 보임)는 경고 없음."""
    analyzer = SquatAnalyzer()
    for i, ang in enumerate(CLEAN_REP):
        analyzer.update(_upright_person(ang), i)
    report = analyzer.finalize()
    codes = {i.code for i in report.video_issues}
    assert "not_side_view" not in codes
    print("✅ 측면 영상은 경고 없음")


def test_front_view_needs_enough_samples() -> None:
    """표본이 적으면(10프레임 미만) 판단을 보류한다."""
    analyzer = SquatAnalyzer()
    for i in range(5):
        analyzer.update(_front_view_person(), i)
    report = analyzer.finalize()
    codes = {i.code for i in report.video_issues}
    assert "not_side_view" not in codes
    print("✅ 표본 부족 시 측면 판정 보류")


# --- 영상이 rep 도중 끝나는 경우 -----------------------------------------

def test_video_ending_mid_rep_is_reported() -> None:
    """앉은 상태(DOWN)에서 영상이 끝나면 조용히 버리지 않고 안내한다."""
    descend_only = [175, 170, 160, 150, 140, 120, 100, 90]
    analyzer = SquatAnalyzer()
    for i, ang in enumerate(descend_only):
        analyzer.update(_upright_person(ang), i)
    report = analyzer.finalize()
    assert report.rep_count == 0
    codes = {i.code for i in report.video_issues}
    assert "ended_mid_rep" in codes, f"도중 종료 미안내: {codes}"
    print("✅ 앉은 채 영상이 끝나면 ended_mid_rep 안내")


def test_completed_rep_has_no_mid_rep_warning() -> None:
    """정상 완료된 rep에는 도중 종료 안내가 붙지 않는다."""
    analyzer = SquatAnalyzer()
    for i, ang in enumerate(CLEAN_REP):
        analyzer.update(_upright_person(ang), i)
    report = analyzer.finalize()
    codes = {i.code for i in report.video_issues}
    assert "ended_mid_rep" not in codes
    print("✅ 완료된 rep에는 도중 종료 안내 없음")


# --- 검출률 게이트 -------------------------------------------------------

def test_detection_gate() -> None:
    low = Report(exercise="스쿼트")
    _detection_gate(low, processed=10, with_person=3)
    assert {i.code for i in low.video_issues} == {"low_detection"}

    ok = Report(exercise="스쿼트")
    _detection_gate(ok, processed=10, with_person=9)
    assert not ok.video_issues
    print("✅ 사람 검출률 낮으면 영상 수준 경고")


if __name__ == "__main__":
    test_smoothing_rejects_spike()
    test_partial_rep_detected()
    test_standing_wobble_is_not_partial()
    test_rep_record_timestamps()
    test_rep_record_without_fps()
    test_front_view_rejected()
    test_side_view_passes()
    test_front_view_needs_enough_samples()
    test_video_ending_mid_rep_is_reported()
    test_completed_rep_has_no_mid_rep_warning()
    test_detection_gate()
    print("\n확장 기능 테스트 통과 🎉")

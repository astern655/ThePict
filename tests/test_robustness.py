"""입력 이상(디코딩 중단·추론 실패·프레임 유실)에 대한 방어 검증.

실행: python -m tests.test_robustness  (또는 pytest)

여기서 확인하는 것은 "정확한 값이 나오는가"가 아니라 "틀린 값을 조용히
내지 않는가"다. 분석이 영상 전체를 못 봤으면 그 사실이 리포트에 남아야 한다.
"""
from __future__ import annotations

from ai.analysis.exercises.squat import SquatAnalyzer
from ai.analysis.feedback import Report
from ai.engine import _decode_gate, _inference_gate
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
    print("\n전체 통과")

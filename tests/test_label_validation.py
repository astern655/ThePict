"""라벨 검사기·rep 매칭 로직 검증 (tools/validate_labels.py).

실영상 없이 돌려야 하므로 엔진 리포트 대신 RepRecord를 직접 만들어 넣는다.
실행: python -m pytest tests/test_label_validation.py
"""
from __future__ import annotations

from ai.analysis.feedback import RepRecord
from tools.validate_labels import check_label_file, derive_label, match_reps


def _label_rep(index: int, start: float, end: float, codes: list[str] | None = None) -> dict:
    codes = codes or []
    return {
        "rep_index": index,
        "start_sec": start,
        "bottom_sec": (start + end) / 2,
        "end_sec": end,
        "label": derive_label(set(codes)),
        "feedback_codes": codes,
    }


def _engine_rep(index: int, start: float, end: float) -> RepRecord:
    fps = 30.0
    return RepRecord(
        rep_index=index,
        start_frame=int(start * fps),
        bottom_frame=int((start + end) / 2 * fps),
        end_frame=int(end * fps),
        start_sec=start,
        bottom_sec=(start + end) / 2,
        end_sec=end,
    )


def _entry(reps: list[dict], **overrides) -> dict:
    entry = {
        "id": "squat_test",
        "video_path": "data/videos/squat_test.mp4",
        "view": "side",
        "expected_rep_count": len(reps),
        "expected_partial_rep_count": 0,
        "expected_video_codes": [],
        "expected_reps": reps,
    }
    entry.update(overrides)
    return entry


# --- 판정 파생 규칙 ------------------------------------------------------

def test_derive_label() -> None:
    assert derive_label(set()) == "correct"
    assert derive_label({"shallow_depth"}) == "needs_work"
    assert derive_label({"shallow_depth", "torso_lean"}) == "needs_work"
    assert derive_label({"very_shallow_depth"}) == "incorrect"
    # ERROR 하나가 WARNING 여러 개를 이긴다
    assert derive_label({"torso_lean", "very_shallow_depth"}) == "incorrect"
    print("✅ 코드 → 판정 파생 규칙이 엔진과 같음")


# --- 라벨 파일 검사 ------------------------------------------------------

def test_clean_label_file_passes() -> None:
    entry = _entry([
        _label_rep(1, 1.0, 3.0),
        _label_rep(2, 4.0, 6.0, ["shallow_depth"]),
        _label_rep(3, 7.0, 9.0, ["very_shallow_depth", "torso_lean"]),
    ])
    assert check_label_file([entry]) == []
    print("✅ 정상 라벨 파일은 오류 없음")


def test_label_contradicting_its_codes_is_caught() -> None:
    """WARNING 코드만 있는데 incorrect로 적으면 잡아야 한다(원래 라벨의 실수)."""
    rep = _label_rep(1, 1.0, 3.0, ["shallow_depth"])
    rep["label"] = "incorrect"
    problems = check_label_file([_entry([rep])])
    assert any("needs_work" in p for p in problems), problems
    print("✅ 코드와 모순된 판정을 잡아냄")


def test_non_side_view_is_rejected() -> None:
    problems = check_label_file([_entry([_label_rep(1, 1.0, 3.0)], view="front")])
    assert any("측면" in p for p in problems), problems
    print("✅ 측면이 아닌 영상을 거부")


def test_same_axis_codes_rejected() -> None:
    """깊이 축 코드를 두 개 적으면 잡아야 한다(한 rep의 깊이는 하나)."""
    rep = _label_rep(1, 1.0, 3.0, ["shallow_depth", "very_shallow_depth"])
    problems = check_label_file([_entry([rep])])
    assert any("축의 코드" in p for p in problems), problems
    print("✅ 같은 축 코드 중복을 잡아냄")


def test_unknown_code_rejected() -> None:
    """삭제된 규칙(knee_forward/too_fast)이 라벨에 남아 있으면 잡아야 한다."""
    rep = _label_rep(1, 1.0, 3.0)
    rep["feedback_codes"] = ["knee_forward"]
    problems = check_label_file([_entry([rep])])
    assert any("알 수 없는 코드" in p for p in problems), problems
    print("✅ 삭제된 규칙 코드를 잡아냄")


def test_rep_count_mismatch_in_label_file() -> None:
    entry = _entry([_label_rep(1, 1.0, 3.0)], expected_rep_count=2)
    problems = check_label_file([entry])
    assert any("expected_rep_count" in p for p in problems), problems
    print("✅ rep 수와 rep 목록 길이 불일치를 잡아냄")


def test_bad_timing_caught() -> None:
    overlapping = _entry([_label_rep(1, 1.0, 5.0), _label_rep(2, 4.0, 8.0)])
    assert any("겹칩니다" in p for p in check_label_file([overlapping]))

    entry = _entry([_label_rep(1, 1.0, 3.0)])
    entry["expected_reps"][0]["bottom_sec"] = 9.0  # start < bottom < end 위반
    assert any("순서" in p for p in check_label_file([entry]))
    print("✅ 구간 시각 오류(순서·겹침)를 잡아냄")


# --- 운동별 스키마 -------------------------------------------------------

def test_pushup_codes_derive_labels() -> None:
    """푸시업도 코드에서 판정이 파생된다(깊이 코드는 스쿼트와 공유)."""
    assert derive_label(set(), "pushup") == "correct"
    assert derive_label({"body_line_break"}, "pushup") == "needs_work"
    assert derive_label({"excessive_body_line_break"}, "pushup") == "incorrect"
    assert derive_label({"shallow_depth", "body_line_break"}, "pushup") == "needs_work"
    assert derive_label({"body_line_break", "very_shallow_depth"}, "pushup") == "incorrect"
    print("✅ 푸시업 코드 → 판정 파생 규칙")


def test_cross_exercise_codes_rejected() -> None:
    """다른 운동의 코드를 섞어 적으면 잡아야 한다.

    깊이 코드는 공유하지만 두 번째 축은 운동마다 다르다. 이걸 안 막으면
    스쿼트 라벨을 푸시업으로 채점해도 조용히 '결함 없음'으로 통과한다.
    """
    rep = _label_rep(1, 1.0, 3.0, ["torso_lean"])          # 스쿼트 코드
    problems = check_label_file([_entry([rep])], "pushup")  # 푸시업으로 검사
    assert any("알 수 없는 코드" in p for p in problems), problems

    rep = _label_rep(1, 1.0, 3.0, ["body_line_break"])      # 푸시업 코드
    problems = check_label_file([_entry([rep])], "squat")   # 스쿼트로 검사
    assert any("알 수 없는 코드" in p for p in problems), problems
    print("✅ 다른 운동의 결함 코드를 잡아냄")


def test_declared_exercise_mismatch_caught() -> None:
    """라벨 파일에 적힌 운동과 검사 중인 운동이 다르면 잡아야 한다."""
    entry = _entry([_label_rep(1, 1.0, 3.0)], exercise="squat")
    problems = check_label_file([entry], "pushup")
    assert any("exercise" in p for p in problems), problems
    # 같으면 통과
    assert check_label_file([_entry([_label_rep(1, 1.0, 3.0)], exercise="squat")], "squat") == []
    print("✅ 라벨 파일의 운동 표기와 검사 대상 불일치를 잡아냄")


def test_pushup_axis_duplicate_rejected() -> None:
    """몸통 축 코드를 두 개 적으면 잡아야 한다(한 rep의 몸통 판정은 하나)."""
    rep = {
        "rep_index": 1, "start_sec": 1.0, "bottom_sec": 2.0, "end_sec": 3.0,
        "label": "incorrect",
        "feedback_codes": ["body_line_break", "excessive_body_line_break"],
    }
    problems = check_label_file([_entry([rep])], "pushup")
    assert any("축의 코드" in p for p in problems), problems
    print("✅ 푸시업 몸통 축 코드 중복을 잡아냄")


# --- rep 매칭 ------------------------------------------------------------

def test_match_by_time_when_counts_equal() -> None:
    labels = [_label_rep(1, 1.0, 3.0), _label_rep(2, 5.0, 7.0)]
    engine = [_engine_rep(1, 1.1, 3.2), _engine_rep(2, 5.1, 7.1)]
    pairs = match_reps(labels, engine)
    assert [(lab["rep_index"], eng.rep_index) for lab, eng in pairs] == [(1, 1), (2, 2)]
    print("✅ 구간 시각으로 rep 짝짓기")


def test_missed_rep_detected() -> None:
    """라벨 3개인데 엔진이 가운데 rep을 놓치면, 나머지 둘은 올바르게 짝지어야 한다."""
    labels = [_label_rep(1, 1.0, 3.0), _label_rep(2, 5.0, 7.0), _label_rep(3, 9.0, 11.0)]
    engine = [_engine_rep(1, 1.1, 3.1), _engine_rep(2, 9.1, 11.1)]  # 2회차 놓침
    pairs = match_reps(labels, engine)
    assert [(lab["rep_index"], eng.rep_index if eng else None) for lab, eng in pairs] == [
        (1, 1), (2, None), (3, 2),
    ]
    print("✅ 미검출 rep을 순번 밀림 없이 식별 (3회차가 엔진 2회차와 짝지어짐)")


def test_spurious_rep_detected() -> None:
    """엔진이 라벨에 없는 rep을 만들어내면 label=None 쌍으로 남는다."""
    labels = [_label_rep(1, 1.0, 3.0)]
    engine = [_engine_rep(1, 1.1, 3.1), _engine_rep(2, 5.0, 7.0)]
    pairs = match_reps(labels, engine)
    assert pairs[0][0] is not None and pairs[0][1].rep_index == 1
    assert pairs[1][0] is None and pairs[1][1].rep_index == 2
    print("✅ 오검출 rep을 식별")


def test_index_fallback_without_times() -> None:
    """라벨에 구간 시각이 없으면 순번으로 짝짓는다."""
    labels = [
        {"rep_index": 1, "label": "correct", "feedback_codes": []},
        {"rep_index": 2, "label": "correct", "feedback_codes": []},
    ]
    engine = [_engine_rep(1, 1.0, 3.0)]
    pairs = match_reps(labels, engine)
    assert pairs[0][1] is not None and pairs[1][1] is None
    print("✅ 시각이 없으면 순번 매칭으로 대체")


if __name__ == "__main__":
    test_derive_label()
    test_clean_label_file_passes()
    test_label_contradicting_its_codes_is_caught()
    test_non_side_view_is_rejected()
    test_same_axis_codes_rejected()
    test_unknown_code_rejected()
    test_rep_count_mismatch_in_label_file()
    test_bad_timing_caught()
    test_pushup_codes_derive_labels()
    test_cross_exercise_codes_rejected()
    test_declared_exercise_mismatch_caught()
    test_pushup_axis_duplicate_rejected()
    test_match_by_time_when_counts_equal()
    test_missed_rep_detected()
    test_spurious_rep_detected()
    test_index_fallback_without_times()
    print("\n라벨 검증 테스트 통과 🎉")

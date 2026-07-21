import pose_eval


def build_keypoints(overrides: dict, default_confidence: float = 0.9) -> list[dict]:
    """Full 17 COCO keypoints; `overrides` maps name -> {"x","y",["confidence"]}."""
    kps = []
    for name in pose_eval.KEYPOINT_NAMES:
        pt = overrides.get(name, {})
        kps.append({
            "name": name,
            "x": pt.get("x", 0.0),
            "y": pt.get("y", 0.0),
            "confidence": pt.get("confidence", default_confidence),
        })
    return kps


def test_angle_90_degrees():
    a = {"x": 1, "y": 0}
    b = {"x": 0, "y": 0}
    c = {"x": 0, "y": 1}
    assert pose_eval.angle(a, b, c) == 90.0


def test_angle_180_degrees():
    a = {"x": -1, "y": 0}
    b = {"x": 0, "y": 0}
    c = {"x": 1, "y": 0}
    assert pose_eval.angle(a, b, c) == 180.0


# geometry: hip=(0,0), shoulder=(0,-40) above it, knee=(40,5) forward,
# ankle=(35,45) placed so knee angle == 90 -> knee/hip/back all in-range
GOOD_SQUAT_OVERRIDES = {
    "left_hip": {"x": 0, "y": 0},
    "left_shoulder": {"x": 0, "y": -40},
    "left_knee": {"x": 40, "y": 5},
    "left_ankle": {"x": 35, "y": 45},
    # low confidence on the right side so the evaluator picks "left"
    "right_hip": {"x": 0, "y": 0, "confidence": 0.1},
    "right_knee": {"x": 40, "y": 5, "confidence": 0.1},
    "right_ankle": {"x": 35, "y": 45, "confidence": 0.1},
    "right_shoulder": {"x": 0, "y": -40, "confidence": 0.1},
}


def test_good_squat_is_scored_well():
    keypoints = build_keypoints(GOOD_SQUAT_OVERRIDES)
    result = pose_eval.evaluate(keypoints, "squat")
    assert result["exercise_id"] == "squat"
    assert result["verdict"] == "good"
    assert result["form_score"] == 100.0
    assert all(c["status"] == "ok" for c in result["checks"])


def test_bad_squat_flags_knee_angle():
    # same hip/back geometry, but ankle placed in line with hip-knee
    # (near-straight leg -> knee angle ~180, outside [70,100])
    overrides = dict(GOOD_SQUAT_OVERRIDES)
    overrides["left_ankle"] = {"x": 80, "y": 10}
    keypoints = build_keypoints(overrides)
    result = pose_eval.evaluate(keypoints, "squat")
    assert result["verdict"] == "needs_improvement"
    assert result["form_score"] < 100.0
    knee_check = next(c for c in result["checks"] if c["name"] == "knee_angle")
    assert knee_check["status"] == "bad"


def test_unsupported_exercise_returns_unsupported_verdict():
    keypoints = build_keypoints(GOOD_SQUAT_OVERRIDES)
    result = pose_eval.evaluate(keypoints, "deadlift")
    assert result == {
        "exercise_id": "deadlift",
        "form_score": 0.0,
        "verdict": "unsupported",
        "checks": [],
    }


def test_is_detected_true_for_high_confidence_frame():
    keypoints = build_keypoints(GOOD_SQUAT_OVERRIDES)
    assert pose_eval.is_detected(keypoints) is True


def test_is_detected_false_for_low_confidence_frame():
    keypoints = build_keypoints({}, default_confidence=0.05)
    assert pose_eval.is_detected(keypoints) is False


def test_is_detected_false_for_empty_keypoints():
    assert pose_eval.is_detected([]) is False

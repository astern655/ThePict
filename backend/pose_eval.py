"""Rule-based pose evaluation. Pure math — no dependency on any pose estimator."""

import math

# COCO 17-keypoint names, in the standard COCO order.
KEYPOINT_NAMES = [
    "nose", "left_eye", "right_eye", "left_ear", "right_ear",
    "left_shoulder", "right_shoulder", "left_elbow", "right_elbow",
    "left_wrist", "right_wrist", "left_hip", "right_hip",
    "left_knee", "right_knee", "left_ankle", "right_ankle",
]

MIN_CONFIDENCE = 0.3  # below this, a keypoint is treated as not detected


def angle(a: dict, b: dict, c: dict) -> float:
    """Angle at vertex b (degrees), formed by points a-b-c."""
    ab = (a["x"] - b["x"], a["y"] - b["y"])
    cb = (c["x"] - b["x"], c["y"] - b["y"])
    dot = ab[0] * cb[0] + ab[1] * cb[1]
    mag_ab = math.hypot(*ab)
    mag_cb = math.hypot(*cb)
    if mag_ab == 0 or mag_cb == 0:
        return 0.0
    cos_theta = max(-1.0, min(1.0, dot / (mag_ab * mag_cb)))
    return math.degrees(math.acos(cos_theta))


def is_detected(keypoints: list[dict]) -> bool:
    """Low-confidence frame -> not enough signal to evaluate a rep."""
    if not keypoints:
        return False
    confident = sum(1 for kp in keypoints if kp.get("confidence", 0) >= MIN_CONFIDENCE)
    return confident >= len(KEYPOINT_NAMES) * 0.7


def _by_name(keypoints: list[dict]) -> dict:
    return {kp["name"]: kp for kp in keypoints}


# TODO(Q5): thresholds are literature rule-of-thumb, not validated against
# real user data yet — revisit once we have labeled squat footage.
RULES = {
    "squat": {
        "knee_angle_min": 70,   # deep squat: knee flexes well past parallel
        "knee_angle_max": 90,   # LLM-FMS + 로컬 정상 rep로 보수적 교정
        "hip_angle_min": 60,
        "hip_angle_max": 100,
        "back_angle_max": 45,  # torso-to-vertical; too high = excessive forward lean
        # --- 영상 분석(AI 엔진) 전용 항목 ---
        # 프레임 단위 evaluate()는 쓰지 않는다. video_analysis.to_set()이 만든 checks를
        # analysis.py가 문장으로 바꿀 때 목표 범위를 여기서 읽는다.
        # 값은 ai/config.py가 원본이며 test_ai_integration.py가 두 값의 일치를 검증한다.
        "squat_depth_max": 30,       # = ai.config.SQUAT_FEMUR_ELEVATION_WARN (rep 최저점 대퇴 거상각)
        "torso_shin_diff_max": 30,   # = ai.config.SQUAT_TORSO_SHIN_DIFF_WARN (상체−정강이 기울기 차)
    },
    "pushup": {
        # 영상 분석 전용. 아래 evaluate()의 프레임 단위 판정은 스쿼트 전용이라
        # 푸시업에는 knee/hip/back 규칙을 두지 않는다(FRAME_RULE_KEYS 참고).
        "pushup_depth_max": 90,     # = ai.config.PUSHUP_GOOD_DEPTH_ANGLE (rep 최저점 팔꿈치각)
        # 몸통은 절대각이 아니라 '시작 자세 기준선 대비 변화량(|델타|)'으로 판정한다.
        "body_line_dev_max": 15,    # = ai.config.PUSHUP_BODY_DELTA_WARN (기준선 대비 이탈 변화량)
    },
}

# evaluate()가 프레임 하나를 판정하려면 이 키들이 다 있어야 한다. 영상 분석 항목만
# 가진 운동(푸시업)은 프레임 단위 판정을 지원하지 않으므로 unsupported로 빠진다.
FRAME_RULE_KEYS = (
    "knee_angle_min", "knee_angle_max",
    "hip_angle_min", "hip_angle_max",
    "back_angle_max",
)


def _check(name: str, value: float, low: float, high: float, message_bad: str) -> dict:
    ok = low <= value <= high
    return {
        "name": name,
        "value": round(value, 1),
        "status": "ok" if ok else "bad",
        "message": "" if ok else message_bad,
    }


def evaluate(keypoints: list[dict], exercise_id: str) -> dict:
    if exercise_id not in RULES or not all(k in RULES[exercise_id] for k in FRAME_RULE_KEYS):
        return {
            "exercise_id": exercise_id,
            "form_score": 0.0,
            "verdict": "unsupported",
            "checks": [],
        }

    rules = RULES[exercise_id]
    pts = _by_name(keypoints)

    # Use the side with higher-confidence keypoints.
    def side_conf(prefix: str) -> float:
        names = [f"{prefix}_hip", f"{prefix}_knee", f"{prefix}_ankle", f"{prefix}_shoulder"]
        vals = [pts[n]["confidence"] for n in names if n in pts]
        return sum(vals) / len(vals) if vals else 0.0

    side = "left" if side_conf("left") >= side_conf("right") else "right"
    hip = pts[f"{side}_hip"]
    knee = pts[f"{side}_knee"]
    ankle = pts[f"{side}_ankle"]
    shoulder = pts[f"{side}_shoulder"]

    knee_angle = angle(hip, knee, ankle)
    hip_angle = angle(shoulder, hip, knee)
    # torso angle vs. vertical, using shoulder-hip line
    vertical_ref = {"x": hip["x"], "y": hip["y"] - 100}
    back_angle = angle(shoulder, hip, vertical_ref)

    checks = [
        _check(
            "knee_angle", knee_angle,
            rules["knee_angle_min"], rules["knee_angle_max"],
            "무릎 각도가 적정 범위를 벗어났습니다",
        ),
        _check(
            "hip_angle", hip_angle,
            rules["hip_angle_min"], rules["hip_angle_max"],
            "고관절 각도가 적정 범위를 벗어났습니다",
        ),
        _check(
            "back_angle", back_angle,
            0, rules["back_angle_max"],
            "허리가 과도하게 숙여졌습니다",
        ),
    ]

    ok_count = sum(1 for c in checks if c["status"] == "ok")
    form_score = round(100 * ok_count / len(checks), 1)
    verdict = "good" if ok_count == len(checks) else "needs_improvement"

    return {
        "exercise_id": exercise_id,
        "form_score": form_score,
        "verdict": verdict,
        "checks": checks,
    }

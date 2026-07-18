from __future__ import annotations

import json
import math
from pathlib import Path

from ai.analysis.exercises.squat import SquatAnalyzer
from ai.pose.keypoints import KP, Keypoint


def _blank() -> list[Keypoint]:
    return [Keypoint(0.0, 0.0, 0.0) for _ in range(17)]


def _set(kp: list[Keypoint], **points: tuple[float, float]) -> list[Keypoint]:
    for name, (x, y) in points.items():
        kp[getattr(KP, name)] = Keypoint(x, y, 0.9)
    return kp


def _hip_for_angle(knee: tuple[float, float], ankle: tuple[float, float], angle_deg: float) -> tuple[float, float]:
    ax, ay = ankle[0] - knee[0], ankle[1] - knee[1]
    length = math.hypot(ax, ay)
    ux, uy = ax / length, ay / length
    th = math.radians(angle_deg)
    return (
        knee[0] + (ux * math.cos(th) - uy * math.sin(th)) * 100.0,
        knee[1] + (ux * math.sin(th) + uy * math.cos(th)) * 100.0,
    )


def _person(knee_angle: float, torso: str) -> list[Keypoint]:
    knee = (300.0, 300.0)
    ankle = (300.0, 400.0)  # 무릎 바로 아래 → 정강이 수직(상체−정강이 차 = 상체 기울기)
    hip = _hip_for_angle(knee, ankle, knee_angle)
    shoulder = (hip[0], hip[1] - 100.0)
    if torso == "leaning":
        # 약 29도 앞기울임 → WARNING(torso_lean) 구간(20~35도)
        shoulder = (hip[0] + 100.0, hip[1] - 180.0)
    return _set(
        _blank(),
        LEFT_HIP=hip,
        LEFT_KNEE=knee,
        LEFT_ANKLE=ankle,
        LEFT_SHOULDER=shoulder,
    )


def test_labeled_squat_feedback_cases() -> None:
    dataset_path = Path(__file__).resolve().parents[1] / "data" / "squat_feedback_cases.json"
    cases = json.loads(dataset_path.read_text(encoding="utf-8"))

    for case in cases:
        analyzer = SquatAnalyzer()
        for frame_index, frame in enumerate(case["frames"]):
            analyzer.update(_person(float(frame["knee_angle"]), frame["torso"]), frame_index)

        report = analyzer.finalize()
        assert report.rep_count == case["expected_rep_count"], case["id"]

        for expected in case["expected_reps"]:
            rep_index = expected["rep_index"]
            actual_codes = {
                issue.code
                for issue in report.issues_for_rep(rep_index)
                if issue.severity.value != "good"
            }
            assert actual_codes == set(expected["feedback_codes"]), case["id"]
            assert report.rep_verdict(rep_index).value == expected["verdict"], case["id"]

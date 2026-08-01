"""케이스 픽스처(data/pushup_feedback_cases.json) 회귀 테스트.

각 케이스는 "이런 시퀀스가 들어오면 이런 판정이 나와야 한다"를 데이터로 적어 둔 것이다.
임계값이나 판정 로직을 건드렸을 때 무엇이 바뀌는지 한눈에 드러난다.
스쿼트의 tests/test_squat_feedback_cases.py와 같은 역할이다.
"""
from __future__ import annotations

import json
from pathlib import Path

from ai.analysis.exercises.pushup import PushupAnalyzer
from tests.test_pushup_logic import _hip_offset_for_deviation, _pushup_person


def test_labeled_pushup_feedback_cases() -> None:
    dataset_path = Path(__file__).resolve().parents[1] / "data" / "pushup_feedback_cases.json"
    cases = json.loads(dataset_path.read_text(encoding="utf-8"))

    for case in cases:
        analyzer = PushupAnalyzer(fps=30.0)
        # 픽스처는 동작 단계를 한 줄씩 적는다. 실영상은 한 단계가 여러 프레임에
        # 걸치므로(25~30fps), 평활 필터가 동작을 지우지 않도록 3프레임으로 늘린다.
        frames = [f for f in case["frames"] for _ in range(3)]
        for frame_index, frame in enumerate(frames):
            # hip_dev는 몸통 일직선 이탈각(도). 양수=엉덩이 처짐, 음수=솟음.
            offset = _hip_offset_for_deviation(abs(float(frame["hip_dev"])))
            if float(frame["hip_dev"]) < 0:
                offset = -offset
            analyzer.update(_pushup_person(float(frame["elbow_angle"]), offset), frame_index)

        report = analyzer.finalize()
        assert report.rep_count == case["expected_rep_count"], case["id"]
        assert report.partial_rep_count == case["expected_partial_rep_count"], case["id"]

        for expected in case["expected_reps"]:
            rep_index = expected["rep_index"]
            actual_codes = {
                issue.code
                for issue in report.issues_for_rep(rep_index)
                if issue.severity.value != "good"
            }
            assert actual_codes == set(expected["feedback_codes"]), (case["id"], actual_codes)
            assert report.rep_verdict(rep_index).value == expected["verdict"], case["id"]


if __name__ == "__main__":
    test_labeled_pushup_feedback_cases()
    print("푸시업 케이스 픽스처 통과 🎉")

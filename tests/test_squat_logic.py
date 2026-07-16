"""AI 분석 로직 단독 검증.

YOLO도 영상도 없이, 가짜 관절 좌표를 만들어 넣어
'각도 계산 → 상태기계 → 반복 카운트'가 맞는지 확인한다.
실행: python -m tests.test_squat_logic
"""
from __future__ import annotations

import math

from ai.analysis.exercises.squat import SquatAnalyzer
from ai.analysis.geometry import angle_at
from ai.pose.keypoints import KP, Keypoint


def _standing_person(knee_angle_deg: float) -> list[Keypoint]:
    """무릎각이 원하는 값이 되도록 엉덩이-무릎-발목을 배치한 가짜 사람.

    무릎(B)을 원점 삼아, 발목은 바로 아래, 엉덩이는 knee_angle만큼 벌어진 방향에 둔다.
    나머지 관절은 검사에 필요한 것만 채운다.
    """
    kp = [Keypoint(0.0, 0.0, 0.0) for _ in range(17)]

    knee = (300.0, 300.0)
    ankle = (300.0, 400.0)  # 무릎 바로 아래(수직 아래 방향 = 화면상 +y)
    # 발목쪽 벡터(0,+1)를 knee_angle 만큼 회전시켜 엉덩이 방향을 만든다.
    # 회전: (0,1) → (-sinθ, cosθ). 그래야 angle_at(hip,knee,ankle)==knee_angle.
    theta = math.radians(knee_angle_deg)
    hip = (knee[0] - 100.0 * math.sin(theta), knee[1] + 100.0 * math.cos(theta))

    dx = 60.0  # 오른다리는 왼다리를 x축으로 평행이동한 복사본 → 같은 무릎각
    for idx, (x, y) in (
        (KP.LEFT_HIP, hip), (KP.RIGHT_HIP, (hip[0] + dx, hip[1])),
        (KP.LEFT_KNEE, knee), (KP.RIGHT_KNEE, (knee[0] + dx, knee[1])),
        (KP.LEFT_ANKLE, ankle), (KP.RIGHT_ANKLE, (ankle[0] + dx, ankle[1])),
        (KP.LEFT_SHOULDER, (hip[0], hip[1] - 100)),
    ):
        kp[idx] = Keypoint(x, y, 0.9)  # confidence 높게 → visible
    return kp


def test_angle_math() -> None:
    # 직각: (0,0)-(0,1)-(1,1) → 90도
    a, b, c = (0.0, 0.0), (0.0, 1.0), (1.0, 1.0)
    assert abs(angle_at(a, b, c) - 90.0) < 1e-6
    # 일직선: 180도
    assert abs(angle_at((0.0, 0.0), (0.0, 1.0), (0.0, 2.0)) - 180.0) < 1e-6
    print("✅ angle_at 계산 정확")


def test_rep_counting() -> None:
    analyzer = SquatAnalyzer()
    # 서있음(170) → 앉음(80) → 서있음(170) 을 3번 반복
    sequence = [170, 140, 90, 80, 90, 140, 170] * 3
    for i, ang in enumerate(sequence):
        analyzer.update(_standing_person(ang), i)
    report = analyzer.finalize()
    assert report.rep_count == 3, f"기대 3회, 실제 {report.rep_count}회"
    print(f"✅ 반복 카운트 정확: {report.rep_count}회")


def test_shallow_depth_flag() -> None:
    analyzer = SquatAnalyzer()
    # 얕게만 앉음: 최저각 120도 → 깊이부족 경고 기대
    sequence = [170, 130, 120, 130, 170]
    for i, ang in enumerate(sequence):
        analyzer.update(_standing_person(ang), i)
    report = analyzer.finalize()
    # 120도는 DOWN 임계(100)보다 커서 rep 성립 안 함 → 카운트 0 확인
    assert report.rep_count == 0
    print("✅ 얕은 스쿼트는 rep로 세지 않음(깊이 임계 동작)")


if __name__ == "__main__":
    test_angle_math()
    test_rep_counting()
    test_shallow_depth_flag()
    print("\n모든 로직 테스트 통과 🎉")

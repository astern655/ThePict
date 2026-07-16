"""AI 분석 로직 단독 검증 (측면 촬영 전용).

YOLO도 영상도 없이, 가짜 관절 좌표를 만들어 넣어
'각도 계산 → 상태기계 → 반복 카운트 → 자세 판정'이 맞는지 확인한다.
실행: python -m tests.test_squat_logic
"""
from __future__ import annotations

import math

from ai.analysis.exercises.squat import SquatAnalyzer, check_torso
from ai.analysis.feedback import RepVerdict
from ai.analysis.geometry import angle_at
from ai.pose.keypoints import KP, Keypoint


def _blank() -> list[Keypoint]:
    """전부 안 보이는(conf 0) 관절 17개."""
    return [Keypoint(0.0, 0.0, 0.0) for _ in range(17)]


def _set(kp: list[Keypoint], **points: tuple[float, float]) -> list[Keypoint]:
    """KP 이름별 좌표를 넣고 visible(conf 0.9) 하게 만든다. 예: _set(kp, LEFT_KNEE=(0,0))."""
    for name, (x, y) in points.items():
        kp[getattr(KP, name)] = Keypoint(x, y, 0.9)
    return kp


def _hip_for_angle(knee: tuple[float, float], ankle: tuple[float, float], angle_deg: float) -> tuple[float, float]:
    """무릎각이 angle_deg가 되도록 엉덩이 위치를 만든다.

    무릎→발목 방향을 angle_deg 만큼 회전시켜 무릎→엉덩이 방향으로 삼는다.
    그러면 angle_at(hip, knee, ankle) == angle_deg.
    """
    ax, ay = ankle[0] - knee[0], ankle[1] - knee[1]
    length = math.hypot(ax, ay)
    ux, uy = ax / length, ay / length
    th = math.radians(angle_deg)
    hx = knee[0] + (ux * math.cos(th) - uy * math.sin(th)) * 100.0
    hy = knee[1] + (ux * math.sin(th) + uy * math.cos(th)) * 100.0
    return (hx, hy)


def _upright_person(knee_angle_deg: float) -> list[Keypoint]:
    """상체를 곧게 세운 정상 자세. 무릎각만 원하는 값으로 준다.

    어깨가 엉덩이 바로 위(같은 x)라 상체 기울기 0도 → torso_lean에 걸리지 않는다.
    """
    knee = (300.0, 300.0)
    ankle = (300.0, 400.0)  # 무릎 바로 아래
    hip = _hip_for_angle(knee, ankle, knee_angle_deg)
    return _set(
        _blank(),
        LEFT_HIP=hip, LEFT_KNEE=knee, LEFT_ANKLE=ankle,
        LEFT_SHOULDER=(hip[0], hip[1] - 100.0),
    )


def _leaning_bottom(knee_angle_deg: float = 80.0) -> list[Keypoint]:
    """최저점에서 상체가 크게 앞으로 숙여진 자세(측면 torso_lean 형태)."""
    knee = (300.0, 300.0)
    ankle = (300.0, 400.0)
    hip = _hip_for_angle(knee, ankle, knee_angle_deg)
    # 어깨가 엉덩이보다 앞(x+160)·위(y-150)로 나가 약 46.8도 앞기울임
    return _set(
        _blank(),
        LEFT_HIP=hip, LEFT_KNEE=knee, LEFT_ANKLE=ankle,
        LEFT_SHOULDER=(hip[0] + 160.0, hip[1] - 150.0),
    )


# --- 순수 계산 ----------------------------------------------------------

def test_angle_math() -> None:
    a, b, c = (0.0, 0.0), (0.0, 1.0), (1.0, 1.0)
    assert abs(angle_at(a, b, c) - 90.0) < 1e-6            # 직각
    assert abs(angle_at((0.0, 0.0), (0.0, 1.0), (0.0, 2.0)) - 180.0) < 1e-6  # 일직선
    print("✅ angle_at 계산 정확")


# --- 반복 카운트 --------------------------------------------------------

def test_rep_counting() -> None:
    analyzer = SquatAnalyzer()
    sequence = [170, 140, 90, 80, 90, 140, 170] * 3
    for i, ang in enumerate(sequence):
        analyzer.update(_upright_person(ang), i)
    report = analyzer.finalize()
    assert report.rep_count == 3, f"기대 3회, 실제 {report.rep_count}회"
    print(f"✅ 반복 카운트 정확: {report.rep_count}회")


def test_shallow_depth_flag() -> None:
    analyzer = SquatAnalyzer()
    sequence = [170, 130, 120, 130, 170]  # 최저 120 → DOWN 임계(100) 못 넘음
    for i, ang in enumerate(sequence):
        analyzer.update(_upright_person(ang), i)
    report = analyzer.finalize()
    assert report.rep_count == 0
    print("✅ 얕은 스쿼트는 rep로 세지 않음(깊이 임계 동작)")


# --- 자세 규칙(순수 함수) -----------------------------------------------

def test_torso_rule() -> None:
    # 어깨가 엉덩이보다 앞(x+)으로 크게 나가 46.8도 기울어진 자세
    leaning = _set(_blank(), LEFT_SHOULDER=(460.0, 150.0), LEFT_HIP=(300.0, 300.0))
    issue = check_torso(leaning, rep=1)
    assert issue is not None and issue.code == "torso_lean"
    upright = _set(_blank(), LEFT_SHOULDER=(300.0, 150.0), LEFT_HIP=(300.0, 300.0))
    assert check_torso(upright, rep=1) is None
    print("✅ 상체 숙임(torso_lean) 규칙 동작 (좌우 자동 선택)")


# --- 통합: 최저점 스냅샷으로 판정하는지 + rep별 종합 판정 ----------------

def test_verdict_correct_on_clean_squat() -> None:
    analyzer = SquatAnalyzer()
    for i, ang in enumerate([170, 140, 90, 80, 90, 140, 170]):
        analyzer.update(_upright_person(ang), i)
    report = analyzer.finalize()
    assert report.rep_count == 1
    assert report.camera_view == "side"
    assert report.rep_verdict(1) is RepVerdict.CORRECT
    print("✅ 깨끗한 스쿼트 → rep 판정 '올바름'")


def test_verdict_uses_bottom_frame() -> None:
    """최저점에만 상체 숙임이 있어도, 서 있는 프레임이 아니라 최저점으로 판정해야 한다."""
    analyzer = SquatAnalyzer()
    sequence = [
        _upright_person(170), _upright_person(140),
        _leaning_bottom(80),                    # 최저점 = 상체 숙임
        _upright_person(140), _upright_person(170),
    ]
    for i, person in enumerate(sequence):
        analyzer.update(person, i)
    report = analyzer.finalize()
    assert report.rep_count == 1
    codes = {i.code for i in report.issues_for_rep(1)}
    assert "torso_lean" in codes, f"최저점 상체 숙임을 못 잡음: {codes}"
    assert report.rep_verdict(1) is RepVerdict.NEEDS_WORK
    print("✅ 최저점 프레임으로 판정 → '교정 필요'(상체 숙임)")


if __name__ == "__main__":
    test_angle_math()
    test_rep_counting()
    test_shallow_depth_flag()
    test_torso_rule()
    test_verdict_correct_on_clean_squat()
    test_verdict_uses_bottom_frame()
    print("\n모든 로직 테스트 통과 🎉")

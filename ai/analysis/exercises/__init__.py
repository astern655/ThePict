"""운동별 분석기 + 레지스트리.

새 운동을 추가하려면:
  1. 이 폴더에 새 파일(예: pushup.py)을 만들고 ExerciseAnalyzer를 상속한다.
  2. 아래 REGISTRY에 한 줄 등록한다.
그러면 엔진이 이름으로 골라 쓸 수 있다.
"""
from __future__ import annotations

from ai.analysis.exercises.base import ExerciseAnalyzer
from ai.analysis.exercises.squat import SquatAnalyzer

# 운동 키 → 분석기 클래스
REGISTRY: dict[str, type[ExerciseAnalyzer]] = {
    "squat": SquatAnalyzer,
}


def create_analyzer(exercise: str) -> ExerciseAnalyzer:
    key = exercise.lower().strip()
    if key not in REGISTRY:
        raise ValueError(
            f"지원하지 않는 운동: {exercise!r}. 사용 가능: {', '.join(REGISTRY)}"
        )
    return REGISTRY[key]()


def available_exercises() -> list[str]:
    return list(REGISTRY)

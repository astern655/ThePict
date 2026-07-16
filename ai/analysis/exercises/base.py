"""모든 운동 분석기가 공유하는 뼈대.

분석기는 프레임을 순서대로 하나씩 받아(update) 내부 상태를 갱신하고,
끝나면 리포트를 낸다(finalize). 이 '스트리밍' 방식이라 긴 영상도 메모리 부담이 적다.
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from ai.analysis.feedback import Report
from ai.pose.detector import Person


class ExerciseAnalyzer(ABC):
    name: str = "exercise"

    def __init__(self) -> None:
        self.report = Report(exercise=self.name)

    @abstractmethod
    def update(self, person: Person | None, frame_index: int) -> None:
        """프레임 한 장 분량의 관절 정보를 받아 상태를 갱신한다.

        person 이 None 이면 그 프레임엔 사람이 안 잡힌 것 → 보통 건너뛴다.
        """

    def finalize(self) -> Report:
        """영상 끝. 최종 리포트를 반환한다."""
        return self.report

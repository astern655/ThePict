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

    def __init__(self, fps: float | None = None) -> None:
        """fps: 영상의 초당 프레임 수. 알면 rep별 시각(초)을 기록할 수 있다.

        None이면(예: 프레임 없이 각도만 넣는 단위 테스트) 시각은 None으로 남고
        프레임 번호만 기록된다.
        """
        self.fps = fps if fps and fps > 0 else None
        self.report = Report(exercise=self.name)

    def seconds(self, frame_index: int) -> float | None:
        """프레임 번호를 영상 시각(초)으로 변환. fps를 모르면 None."""
        if self.fps is None:
            return None
        return round(frame_index / self.fps, 2)

    def hud_lines(self) -> list[str]:
        """주석 영상 좌상단 HUD에 띄울 문장들. (cv2 폰트 한계로 영어만)"""
        return [f"Reps: {self.report.rep_count}"]

    @abstractmethod
    def update(self, person: Person | None, frame_index: int) -> None:
        """프레임 한 장 분량의 관절 정보를 받아 상태를 갱신한다.

        person 이 None 이면 그 프레임엔 사람이 안 잡힌 것 → 보통 건너뛴다.
        """

    def finalize(self) -> Report:
        """영상 끝. 최종 리포트를 반환한다."""
        return self.report

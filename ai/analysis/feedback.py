"""피드백을 담는 자료구조.

운동 분석기는 '결함(Issue)'을 만들어 모으고, 마지막에 리포트로 합친다.
문자열을 여기저기서 조립하지 않고 구조화해 두면 UI/서버 응답 어디에도 재사용된다.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class Severity(str, Enum):
    GOOD = "good"       # 잘한 점
    WARNING = "warning"  # 개선 권장
    ERROR = "error"      # 명확한 자세 결함


@dataclass
class Issue:
    """한 rep에서 발견된 하나의 피드백 항목."""
    rep_index: int          # 몇 번째 반복인가 (1부터)
    code: str               # 규칙 식별자 예: "shallow_depth"
    severity: Severity
    message: str            # 사용자에게 보여줄 한국어 문장
    measured: float | None = None  # 측정값 (디버깅/표시용)

    def to_dict(self) -> dict:
        return {
            "rep_index": self.rep_index,
            "code": self.code,
            "severity": self.severity.value,
            "message": self.message,
            "measured": self.measured,
        }


@dataclass
class Report:
    """영상 하나에 대한 최종 분석 결과."""
    exercise: str
    rep_count: int = 0
    issues: list[Issue] = field(default_factory=list)
    frames_processed: int = 0
    frames_with_person: int = 0
    annotated_video_path: str | None = None

    def add(self, issue: Issue) -> None:
        self.issues.append(issue)

    def summary_lines(self) -> list[str]:
        """UI에 뿌리기 좋은 요약 문장 리스트."""
        lines = [f"운동: {self.exercise}", f"총 반복: {self.rep_count}회"]
        if not self.issues:
            lines.append("특이 결함 없이 안정적인 자세였습니다. 👍")
            return lines
        for iss in self.issues:
            mark = {"good": "✅", "warning": "⚠️", "error": "❌"}[iss.severity.value]
            lines.append(f"{mark} [{iss.rep_index}회차] {iss.message}")
        return lines

    def to_dict(self) -> dict:
        """서버가 JSON으로 그대로 내려줄 수 있는 형태."""
        return {
            "exercise": self.exercise,
            "rep_count": self.rep_count,
            "frames_processed": self.frames_processed,
            "frames_with_person": self.frames_with_person,
            "annotated_video_path": self.annotated_video_path,
            "issues": [i.to_dict() for i in self.issues],
            "summary": self.summary_lines(),
        }

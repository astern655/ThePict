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


class RepVerdict(str, Enum):
    """한 rep(반복)의 자세가 올바른지에 대한 종합 판정."""
    CORRECT = "correct"          # 올바름 (결함 없음)
    NEEDS_WORK = "needs_work"    # 교정 필요 (경고 수준 결함)
    INCORRECT = "incorrect"      # 잘못됨 (명확한 결함)


# 판정 → 사용자에게 보여줄 한국어 라벨/표식
_VERDICT_LABEL: dict[RepVerdict, str] = {
    RepVerdict.CORRECT: "올바름",
    RepVerdict.NEEDS_WORK: "교정 필요",
    RepVerdict.INCORRECT: "잘못됨",
}
_VERDICT_MARK: dict[RepVerdict, str] = {
    RepVerdict.CORRECT: "🟢",
    RepVerdict.NEEDS_WORK: "🟡",
    RepVerdict.INCORRECT: "🔴",
}


def verdict_from_issues(issues: list["Issue"]) -> RepVerdict:
    """한 rep의 결함 목록으로 종합 판정을 매긴다.

    가장 심각한 결함이 기준: ERROR 하나라도 있으면 '잘못됨',
    ERROR는 없고 WARNING이 있으면 '교정 필요', 둘 다 없으면 '올바름'.
    (GOOD 항목은 판정을 낮추지 않는다.)
    """
    severities = {i.severity for i in issues}
    if Severity.ERROR in severities:
        return RepVerdict.INCORRECT
    if Severity.WARNING in severities:
        return RepVerdict.NEEDS_WORK
    return RepVerdict.CORRECT


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
    camera_view: str = "side"  # 스쿼트는 측면 촬영만 받는다(항상 "side")

    def add(self, issue: Issue) -> None:
        self.issues.append(issue)

    def issues_for_rep(self, rep_index: int) -> list[Issue]:
        """특정 rep에서 나온 결함만 골라 반환."""
        return [i for i in self.issues if i.rep_index == rep_index]

    def rep_verdict(self, rep_index: int) -> RepVerdict:
        """특정 rep의 자세가 올바른지 종합 판정."""
        return verdict_from_issues(self.issues_for_rep(rep_index))

    def rep_verdicts(self) -> list[dict]:
        """rep마다 '올바름/교정 필요/잘못됨' 판정을 매긴 목록.

        UI/서버가 rep별로 초록·노랑·빨강을 칠하는 데 그대로 쓴다.
        """
        out = []
        for rep in range(1, self.rep_count + 1):
            v = self.rep_verdict(rep)
            out.append({
                "rep_index": rep,
                "verdict": v.value,
                "label": _VERDICT_LABEL[v],
            })
        return out

    def verdict_counts(self) -> dict[str, int]:
        """판정별 rep 수 집계 (올바름 몇 회, 교정 필요 몇 회 …)."""
        counts = {v.value: 0 for v in RepVerdict}
        for rep in range(1, self.rep_count + 1):
            counts[self.rep_verdict(rep).value] += 1
        return counts

    def summary_lines(self) -> list[str]:
        """UI에 뿌리기 좋은 요약 문장 리스트."""
        lines = [f"운동: {self.exercise}", f"총 반복: {self.rep_count}회"]

        # rep별 종합 판정을 한눈에
        if self.rep_count:
            c = self.verdict_counts()
            lines.append(
                f"자세 판정 — 올바름 {c['correct']}회 · "
                f"교정 필요 {c['needs_work']}회 · 잘못됨 {c['incorrect']}회"
            )
            for rep in range(1, self.rep_count + 1):
                v = self.rep_verdict(rep)
                detail = "; ".join(
                    i.message for i in self.issues_for_rep(rep)
                    if i.severity is not Severity.GOOD
                )
                line = f"{_VERDICT_MARK[v]} [{rep}회차] {_VERDICT_LABEL[v]}"
                lines.append(f"{line} — {detail}" if detail else line)
            return lines

        if not self.issues:
            lines.append("특이 결함 없이 안정적인 자세였습니다. 👍")
        return lines

    def to_dict(self) -> dict:
        """서버가 JSON으로 그대로 내려줄 수 있는 형태."""
        return {
            "exercise": self.exercise,
            "rep_count": self.rep_count,
            "camera_view": self.camera_view,
            "frames_processed": self.frames_processed,
            "frames_with_person": self.frames_with_person,
            "annotated_video_path": self.annotated_video_path,
            "issues": [i.to_dict() for i in self.issues],
            "rep_verdicts": self.rep_verdicts(),
            "verdict_counts": self.verdict_counts(),
            "summary": self.summary_lines(),
        }

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
    """한 rep에서 발견된 하나의 피드백 항목.

    rep_index=0 은 특정 rep이 아니라 영상 전체에 대한 항목이라는 뜻이다
    (예: 측면 촬영이 아님, 사람 검출률 낮음). Report.video_issues에 담긴다.
    """
    rep_index: int          # 몇 번째 반복인가 (1부터, 0=영상 전체)
    code: str               # 규칙 식별자 예: "shallow_depth"
    severity: Severity
    message: str            # 사용자에게 보여줄 한국어 문장
    measured: float | None = None  # 측정값 (디버깅/표시용)
    # 이 항목을 발생시킨 기준선. measured와 같은 지표·같은 단위여야 한다.
    # (예: torso_lean이면 상체−정강이 차의 WARNING 임계값 30.0)
    # 임계값이 나중에 바뀌어도 저장된 리포트를 그대로 해석할 수 있게 함께 남긴다.
    # 넘는 쪽이 결함인지 모자란 쪽이 결함인지는 코드마다 다르다. rep 결함(깊이·상체·
    # 몸통 델타)은 전부 '초과가 결함'이고, 영상 수준의 low_detection·no_body_baseline
    # (캘리브레이션 표본 수 미달)만 '미만이 결함'이다.
    threshold: float | None = None

    def to_dict(self) -> dict:
        return {
            "rep_index": self.rep_index,
            "code": self.code,
            "severity": self.severity.value,
            "message": self.message,
            "measured": self.measured,
            "threshold": self.threshold,
        }


@dataclass
class RepRecord:
    """한 rep의 구간 정보(어느 프레임/몇 초에 일어났는가).

    UI가 "3회차가 잘못됐다" 피드백을 영상의 해당 구간으로 바로 연결(시킹)
    할 수 있게 한다. *_sec 값들은 fps를 알 때만 채워진다(모르면 None).
    """
    rep_index: int
    start_frame: int        # 내려가기 시작한 프레임
    bottom_frame: int       # 가장 깊이 앉은 프레임
    end_frame: int          # 완전히 일어선 프레임
    bottom_angle: float | None = None  # 최저점 관절각(스쿼트면 무릎각)
    # 최저점의 원시 측정값. 결함일 때만 Issue로 남는 값(상체 앞숙임)은 정상 rep에서
    # 아무 데도 기록되지 않아 "올바른 스쿼트의 실제 분포"를 볼 수 없었다. 임계값을
    # 데이터로 재검증하려면 판정과 무관하게 매 rep의 측정값이 남아야 한다.
    # (docs/SQUAT_TUNING.md §3) 관절이 안 보여 못 잰 경우에만 None.
    # 운동별로 쓰는 칸이 다르다(스쿼트는 상체·정강이, 푸시업은 몸통 일직선).
    # 세 번째 운동이 또 다른 지표를 들고 오면 dict 한 칸으로 바꾸는 게 낫다.
    bottom_femur_elevation: float | None = None  # [스쿼트] 대퇴 거상각(수평 기준, 도) — 깊이 판정 지표
    bottom_hip_in_span: float | None = None    # [스쿼트] 엉덩이의 무릎~발목 구간 내 위치(측정 전용)
    bottom_torso_incline: float | None = None  # [스쿼트] 상체 기울기(수직 기준, 도)
    bottom_shin_incline: float | None = None   # [스쿼트] 정강이 기울기(수직 기준, 도)
    bottom_torso_shin_diff: float | None = None  # [스쿼트] 상체 − 정강이 (판정 지표)
    bottom_body_line_dev: float | None = None  # [푸시업] 최저점 몸통 이탈각(도, 기록 전용)
    top_body_line_dev: float | None = None     # [푸시업] top 자세 몸통 이탈각(도, 크기)
    # [푸시업] top 이탈각(부호: +처짐/−솟음)의 기준선 대비 변화량 — 판정 지표.
    # 기준선(Report.body_line_baseline)이나 이번 rep의 부호 표본이 없으면 None.
    top_body_line_delta: float | None = None
    start_sec: float | None = None
    bottom_sec: float | None = None
    end_sec: float | None = None
    duration_sec: float | None = None  # rep 전체 소요 시간
    descent_sec: float | None = None   # 내려가는 데 걸린 시간
    ascent_sec: float | None = None    # 올라오는 데 걸린 시간

    def to_dict(self) -> dict:
        return {
            "rep_index": self.rep_index,
            "start_frame": self.start_frame,
            "bottom_frame": self.bottom_frame,
            "end_frame": self.end_frame,
            "bottom_angle": self.bottom_angle,
            "bottom_femur_elevation": self.bottom_femur_elevation,
            "bottom_hip_in_span": self.bottom_hip_in_span,
            "bottom_torso_incline": self.bottom_torso_incline,
            "bottom_shin_incline": self.bottom_shin_incline,
            "bottom_torso_shin_diff": self.bottom_torso_shin_diff,
            "bottom_body_line_dev": self.bottom_body_line_dev,
            "top_body_line_dev": self.top_body_line_dev,
            "top_body_line_delta": self.top_body_line_delta,
            "start_sec": self.start_sec,
            "bottom_sec": self.bottom_sec,
            "end_sec": self.end_sec,
            "duration_sec": self.duration_sec,
            "descent_sec": self.descent_sec,
            "ascent_sec": self.ascent_sec,
        }


@dataclass
class Report:
    """영상 하나에 대한 최종 분석 결과."""
    exercise: str
    rep_count: int = 0
    issues: list[Issue] = field(default_factory=list)
    reps: list[RepRecord] = field(default_factory=list)  # rep별 구간/시각 정보
    video_issues: list[Issue] = field(default_factory=list)  # 영상 전체 수준 경고
    partial_rep_count: int = 0  # 깊이가 모자라 rep로 인정 못 한 움직임 수
    frames_processed: int = 0
    frames_with_person: int = 0
    frames_skipped: int = 0        # 디코딩 실패로 건너뛴 프레임
    frames_detect_failed: int = 0  # 관절 추론이 예외로 실패한 프레임
    tracking_gap_count: int = 0    # 추적이 끊긴 구간 수
    dropped_rep_count: int = 0     # 추적 끊김으로 폐기한 진행 중 rep 수
    annotated_video_path: str | None = None
    camera_view: str = "side"  # 스쿼트는 측면 촬영만 받는다(항상 "side")
    # [푸시업] 첫 dip 이전 top 자세에서 잰 몸통 이탈각 기준선(부호: +처짐/−솟음).
    # 캘리브레이션 구간이 짧아 못 재면 None — rep의 델타 판정도 함께 보류된다.
    body_line_baseline: float | None = None

    def add(self, issue: Issue) -> None:
        self.issues.append(issue)

    def add_video_issue(self, issue: Issue) -> None:
        """특정 rep이 아닌 영상 전체에 대한 경고를 추가한다(rep_index=0)."""
        self.video_issues.append(issue)

    def rep_record(self, rep_index: int) -> RepRecord | None:
        """특정 rep의 구간 정보(없으면 None)."""
        for r in self.reps:
            if r.rep_index == rep_index:
                return r
        return None

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
            entry = {
                "rep_index": rep,
                "verdict": v.value,
                "label": _VERDICT_LABEL[v],
            }
            # 구간 정보가 있으면 UI가 바로 시킹할 수 있게 시각을 붙인다.
            record = self.rep_record(rep)
            if record is not None:
                entry["start_sec"] = record.start_sec
                entry["bottom_sec"] = record.bottom_sec
                entry["end_sec"] = record.end_sec
            out.append(entry)
        return out

    def verdict_counts(self) -> dict[str, int]:
        """판정별 rep 수 집계 (올바름 몇 회, 교정 필요 몇 회 …)."""
        counts = {v.value: 0 for v in RepVerdict}
        for rep in range(1, self.rep_count + 1):
            counts[self.rep_verdict(rep).value] += 1
        return counts

    def _rep_coaching_lines(self, rep: int) -> list[str]:
        """한 rep의 판정 헤더 + 결함별 '무엇을 어떻게' 안내 줄.

        헤더에 최저점 시각을 붙여 UI/사용자가 영상의 해당 지점을 바로 찾게 한다.
        fps를 모르면 bottom_sec이 None이므로 시각 없이 헤더만 낸다.
        """
        v = self.rep_verdict(rep)
        header = f"{_VERDICT_MARK[v]} {rep}회차 · {_VERDICT_LABEL[v]}"
        record = self.rep_record(rep)
        if record is not None and record.bottom_sec is not None:
            header += f" · 최저점 {record.bottom_sec:.2f}초"
        out = [header]

        # GOOD 항목은 결함이 아니므로 교정 안내에서 뺀다.
        for issue in self.issues_for_rep(rep):
            if issue.severity is Severity.GOOD:
                continue
            line = f"   └ {issue.message}"
            if issue.measured is not None and issue.threshold is not None:
                line += f" (측정 {issue.measured}° / 기준 {issue.threshold}° 이하)"
            elif issue.measured is not None:
                line += f" (측정 {issue.measured}°)"
            out.append(line)
        return out

    def summary_lines(self) -> list[str]:
        """UI에 뿌리기 좋은 요약 문장 리스트."""
        lines = [f"운동: {self.exercise}", f"총 반복: {self.rep_count}회"]

        # 영상 전체 수준 경고(측면 아님·검출률 낮음 등)는 맨 위에서 알린다.
        for vi in self.video_issues:
            lines.append(f"⚠️ {vi.message}")
        if self.partial_rep_count:
            lines.append(f"부분 반복 {self.partial_rep_count}회 (깊이가 얕아 횟수에서 제외)")

        # rep별 종합 판정을 한눈에
        if self.rep_count:
            c = self.verdict_counts()
            lines.append(
                f"자세 판정 — 올바름 {c['correct']}회 · "
                f"교정 필요 {c['needs_work']}회 · 잘못됨 {c['incorrect']}회"
            )
            for rep in range(1, self.rep_count + 1):
                lines.extend(self._rep_coaching_lines(rep))
            return lines

        if not self.issues:
            lines.append("특이 결함 없이 안정적인 자세였습니다. 👍")
        return lines

    def to_dict(self) -> dict:
        """서버가 JSON으로 그대로 내려줄 수 있는 형태."""
        return {
            "exercise": self.exercise,
            "rep_count": self.rep_count,
            "partial_rep_count": self.partial_rep_count,
            "camera_view": self.camera_view,
            "frames_processed": self.frames_processed,
            "frames_with_person": self.frames_with_person,
            "frames_skipped": self.frames_skipped,
            "frames_detect_failed": self.frames_detect_failed,
            "tracking_gap_count": self.tracking_gap_count,
            "dropped_rep_count": self.dropped_rep_count,
            "annotated_video_path": self.annotated_video_path,
            "body_line_baseline": self.body_line_baseline,
            "issues": [i.to_dict() for i in self.issues],
            "video_issues": [i.to_dict() for i in self.video_issues],
            "reps": [r.to_dict() for r in self.reps],
            "rep_verdicts": self.rep_verdicts(),
            "verdict_counts": self.verdict_counts(),
            "summary": self.summary_lines(),
        }

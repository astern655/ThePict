"""모든 운동 분석기가 공유하는 뼈대.

분석기는 프레임을 순서대로 하나씩 받아(update) 내부 상태를 갱신하고,
끝나면 리포트를 낸다(finalize). 이 '스트리밍' 방식이라 긴 영상도 메모리 부담이 적다.

두 계층이다.

- `ExerciseAnalyzer` — 최소 계약(update/finalize)만 정의. 반복이 없는 운동
  (플랭크 등)을 나중에 붙일 수 있게 열어 둔다.
- `AngleRepAnalyzer` — "관절각 하나가 오르내리는" 운동(스쿼트=무릎각,
  푸시업=팔꿈치각)의 공통 처리. 히스테리시스 상태기계, 최저점 스냅샷,
  부분 반복, 추적 끊김 대응, 측면 촬영 검증이 여기 한 벌만 있다.
"""
from __future__ import annotations

import math
import statistics
from abc import ABC, abstractmethod

from ai.analysis.feedback import Issue, RepRecord, Report, Severity
from ai.analysis.filters import MedianSmoother
from ai.analysis.landmarks import side_view_ratio
from ai.config import (
    MAX_TRACKING_GAP_FRAMES,
    MAX_TRACKING_GAP_SEC,
    SIDE_VIEW_MIN_SAMPLES,
    SIDE_VIEW_RATIO_MAX,
)
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


class AngleRepAnalyzer(ExerciseAnalyzer):
    """관절각 하나로 반복을 세는 운동의 공통 분석기.

    하위 클래스가 채워야 하는 것:
      - 임계값 4개(`down_angle` / `up_angle` / `partial_dip_angle` / `smooth_window`)
      - `measure_angle()` — 이 운동의 기준 관절각(스쿼트=무릎, 푸시업=팔꿈치)
      - `check_form()`   — 최저점 스냅샷으로 자세를 판정해 Issue 목록을 반환
      - 안내 문구 몇 개(`ended_mid_rep_message` 등)

    각도가 클수록 '펴진 상태'라고 가정한다(무릎각·팔꿈치각 모두 그렇다).
    """

    # --- 하위 클래스가 정의하는 임계값 -----------------------------------
    down_angle: float          # 이보다 작아지면 '내려감(DOWN)'
    up_angle: float            # 이보다 커지면 '올라옴(UP)' → rep 완료
    partial_dip_angle: float   # DOWN까지는 못 갔지만 이 아래로 내려갔으면 부분 반복
    smooth_window: int         # 중앙값 필터 윈도(1이면 비활성)
    # rep 인정 깊이 가드(도). DOWN→UP을 완주했더라도 최저각이
    # (down_angle − 이 값)까지 내려가지 못한 dip은 rep 대신 부분 반복으로 센다.
    # 임계선을 살짝 스치는 가짜 dip(잔떨림·피로 구간) 방어용. 0이면 비활성.
    rep_prominence: float = 0.0
    # 측면 판정 경계. 자세(선 자세 vs 엎드린 자세)에 따라 같은 지표의 정상 범위가
    # 달라져 운동별로 다시 정할 수 있게 열어 둔다.
    side_view_ratio_max: float = SIDE_VIEW_RATIO_MAX

    # --- 안내 문구 --------------------------------------------------------
    ended_mid_rep_message: str = "동작 도중에 영상이 끝나 마지막 1회는 횟수에 포함되지 않았습니다."
    partial_rep_message: str = "동작 범위가 모자라 횟수에서 제외된 움직임이 {n}회 있습니다."
    not_side_view_message: str = (
        "측면 촬영이 아닌 것으로 보입니다. 옆에서 다시 촬영해 주세요. "
        "(정면 영상에서는 자세 판정이 부정확합니다)"
    )
    hud_angle_label: str = "Angle"

    def __init__(self, fps: float | None = None) -> None:
        super().__init__(fps)
        self.state = "UP"               # 시작은 펴진 자세라고 가정
        self.min_angle_in_rep = 180.0   # 현재 rep에서 관측된 최소각(평활값)
        self._bottom_person: Person | None = None  # 최소각 프레임의 관절 스냅샷
        self._bottom_frame = 0          # 최소각이 나온 프레임 번호
        self._smoother = MedianSmoother(self.smooth_window)
        self._last_angle: float | None = None      # HUD 표시용 최근 평활 각
        # '내려감(dip)' 추적: UP 임계 아래로 내려간 구간. rep이 되면 시작점으로,
        # DOWN까지 못 가고 끝나면 부분 반복(partial rep)으로 쓴다.
        self._dip_start_frame: int | None = None
        self._dip_min = 180.0
        self._view_ratios: list[float] = []        # 측면 검증 표본
        # 추적 끊김 처리: 마지막으로 각을 실제로 잰 프레임 번호.
        self._last_measured_frame: int | None = None
        # 끊김 직후에는 '완전히 펴진 자세'를 한 번 다시 볼 때까지 카운트를 멈춘다.
        self._await_standing = False

    # --- 하위 클래스 훅 ---------------------------------------------------

    @abstractmethod
    def measure_angle(self, person: Person) -> float | None:
        """이 운동의 기준 관절각. 필요한 관절이 안 보이면 None."""

    @abstractmethod
    def check_form(self, rep: int, bottom_person: Person | None,
                   min_angle: float) -> list[Issue]:
        """rep 최저점 자세를 판정해 Issue 목록을 반환한다(없으면 빈 리스트).

        bottom_person이 None이면 최저점 관절을 못 본 것이다.
        """

    def record_bottom_measurements(self, record: RepRecord) -> None:
        """최저점 원시 측정값을 rep 기록에 남긴다(기본: 남길 것 없음).

        판정 여부와 무관하게 숫자를 남겨야 임계값을 데이터로 재검증할 수 있다.
        """

    # --- 공통 처리 --------------------------------------------------------

    def _max_gap_frames(self) -> int:
        """추적 끊김으로 볼 프레임 간격. fps를 알면 초 단위 기준으로 환산한다."""
        if self.fps is None:
            return MAX_TRACKING_GAP_FRAMES
        return max(1, round(self.fps * MAX_TRACKING_GAP_SEC))

    def _handle_gap(self) -> None:
        """유실 구간이 임계보다 길 때: 진행 중이던 rep을 폐기하고 필터를 비운다.

        유실 구간을 없던 시간처럼 이어붙이면 (1) 최저점을 놓쳐 동작 범위가 실제보다
        얕게 판정되고 (2) 유실 전후 값이 중앙값 필터에서 이웃으로 섞인다.
        조용히 틀린 값을 내느니 그 rep을 버리고 사실을 남기는 편이 낫다.
        """
        self.report.tracking_gap_count += 1
        if self.state == "DOWN" or self._dip_start_frame is not None:
            self.report.dropped_rep_count += 1
        self.state = "UP"
        self._await_standing = True
        self._smoother.reset()
        self._reset_rep_tracking()

    def update(self, person: Person | None, frame_index: int) -> None:
        if person is None:
            return

        ratio = side_view_ratio(person)
        if ratio is not None:
            self._view_ratios.append(ratio)

        raw_angle = self.measure_angle(person)
        # NaN은 모든 비교가 False라 상태기계를 조용히 멈춘다. 하위 클래스가
        # 무엇을 반환하든 여기서 한 번 더 막는다(못 잰 프레임과 같게 취급).
        if raw_angle is None or not math.isfinite(raw_angle):
            return

        # 직전에 각을 잰 프레임과의 간격으로 유실 구간 길이를 판단한다.
        # (사람 미검출·관절 미가시·추론 실패 프레임은 모두 여기서 '간격'으로 나타난다)
        if (
            self._last_measured_frame is not None
            and frame_index - self._last_measured_frame > self._max_gap_frames()
        ):
            self._handle_gap()
        self._last_measured_frame = frame_index

        angle = self._smoother.push(raw_angle)
        self._last_angle = angle

        # 끊김 직후: 완전히 펴진 자세를 다시 볼 때까지 상태기계를 진행하지 않는다.
        if self._await_standing:
            if angle <= self.up_angle:
                return
            self._await_standing = False

        # --- dip(내려감 구간) 추적: 시작·최소각 ---
        if angle < self.up_angle:
            if self._dip_start_frame is None:
                self._dip_start_frame = frame_index
            self._dip_min = min(self._dip_min, angle)

        # 내려가는 동안 최소각을 추적하고, 그 순간의 관절을 통째로 붙든다.
        # 자세 판정은 이 '가장 깊이 내려간 프레임'으로 해야 의미가 있다.
        if self.state == "DOWN" or angle < self.up_angle:
            if angle < self.min_angle_in_rep:
                self.min_angle_in_rep = angle
                self._bottom_person = person
                self._bottom_frame = frame_index

        # --- 상태기계 ---
        if self.state == "UP":
            if angle < self.down_angle:
                self.state = "DOWN"
            elif angle > self.up_angle and self._dip_start_frame is not None:
                # DOWN까지 못 간 채 다시 올라옴 → 충분히 내려갔었다면 부분 반복
                if self._dip_min < self.partial_dip_angle:
                    self.report.partial_rep_count += 1
                self._reset_rep_tracking()
        elif self.state == "DOWN" and angle > self.up_angle:
            # DOWN → UP 전환 = 반복 1회 완료 후보. 깊이 가드를 통과해야 rep이다.
            self.state = "UP"
            if self.min_angle_in_rep <= self.down_angle - self.rep_prominence:
                self.report.rep_count += 1
                self._finish_rep(self.report.rep_count, frame_index)
            else:
                # DOWN 임계를 스치기만 한 얕은 dip — 조용히 버리지 않고
                # 부분 반복으로 집계해 사용자에게 알린다.
                self.report.partial_rep_count += 1
            self._reset_rep_tracking()

    def _reset_rep_tracking(self) -> None:
        self.min_angle_in_rep = 180.0
        self._bottom_person = None
        self._dip_start_frame = None
        self._dip_min = 180.0

    def _finish_rep(self, rep: int, end_frame: int) -> None:
        """방금 끝난 rep의 구간 정보를 기록하고 자세 규칙을 검사한다."""
        start_frame = self._dip_start_frame if self._dip_start_frame is not None else end_frame
        record = RepRecord(
            rep_index=rep,
            start_frame=start_frame,
            bottom_frame=self._bottom_frame,
            end_frame=end_frame,
            bottom_angle=round(self.min_angle_in_rep, 1),
            start_sec=self.seconds(start_frame),
            bottom_sec=self.seconds(self._bottom_frame),
            end_sec=self.seconds(end_frame),
        )
        self.record_bottom_measurements(record)
        if self.fps is not None:
            record.duration_sec = round((end_frame - start_frame) / self.fps, 2)
            record.descent_sec = round((self._bottom_frame - start_frame) / self.fps, 2)
            record.ascent_sec = round((end_frame - self._bottom_frame) / self.fps, 2)
        self.report.reps.append(record)
        for issue in self.check_form(rep, self._bottom_person, self.min_angle_in_rep):
            self.report.add(issue)

    def _side_view_issue(self) -> Issue | None:
        """측면 촬영 검증. 표본이 충분한데 어깨가 넓게 벌어져 보이면 정면 촬영이다.

        운동별로 추가 지표가 필요하면 오버라이드한다(푸시업은 3중 게이트).
        """
        if len(self._view_ratios) < SIDE_VIEW_MIN_SAMPLES:
            return None
        ratio = statistics.median(self._view_ratios)
        if ratio > self.side_view_ratio_max:
            return Issue(
                rep_index=0, code="not_side_view", severity=Severity.ERROR,
                message=self.not_side_view_message,
                measured=round(ratio, 2), threshold=self.side_view_ratio_max,
            )
        return None

    def finalize(self) -> Report:
        issue = self._side_view_issue()
        if issue is not None:
            self.report.add_video_issue(issue)

        # 내려간 상태(DOWN)에서 영상이 끝나면 그 rep은 상태기계가 완료를 못 본다.
        # 조용히 버리지 않고, 횟수에서 빠졌음을 안내한다(동작 범위 부족과는 다른 사유).
        if self.state == "DOWN":
            self.report.add_video_issue(Issue(
                rep_index=0, code="ended_mid_rep", severity=Severity.WARNING,
                message=self.ended_mid_rep_message,
                measured=round(self.min_angle_in_rep, 1),
            ))

        # 추적이 끊긴 구간이 있으면 '몇 회가 왜 빠졌는지'를 남긴다.
        if self.report.tracking_gap_count:
            msg = (f"관절 추적이 {self.report.tracking_gap_count}번 끊겼습니다. "
                   f"전신이 화면 안에 계속 들어오도록 촬영해 주세요.")
            if self.report.dropped_rep_count:
                msg += (f" 끊긴 구간에 걸친 동작 {self.report.dropped_rep_count}회는 "
                        f"정확히 잴 수 없어 횟수에서 제외했습니다.")
            self.report.add_video_issue(Issue(
                rep_index=0, code="tracking_gap", severity=Severity.WARNING,
                message=msg, measured=float(self.report.tracking_gap_count),
            ))

        if self.report.partial_rep_count:
            self.report.add_video_issue(Issue(
                rep_index=0, code="partial_reps", severity=Severity.WARNING,
                message=self.partial_rep_message.format(n=self.report.partial_rep_count),
                measured=float(self.report.partial_rep_count),
            ))
        return self.report

    def hud_lines(self) -> list[str]:
        lines = [f"Reps: {self.report.rep_count}", f"State: {self.state}"]
        if self._last_angle is not None:
            lines.append(f"{self.hud_angle_label}: {self._last_angle:.0f} deg")
        return lines

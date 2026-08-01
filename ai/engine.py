"""AI 엔진의 공개 진입점.

백엔드 서버는 이 파일의 analyze_video() 하나만 호출하면 된다.
내부적으로 '프레임 읽기 → YOLO 관절검출 → 운동 분석 → (선택)주석영상 저장'을 엮는다.
"""
from __future__ import annotations

from pathlib import Path

import cv2

from ai.analysis.exercises import create_analyzer
from ai.analysis.feedback import Issue, Report, RepVerdict, Severity
from ai.config import (
    MAX_DETECT_FAILURE_RATIO,
    MIN_PERSON_RATIO,
    OUTPUT_DIR,
    pose_model_for,
    VIDEO_FPS_FALLBACK,
    VIDEO_FPS_MAX,
    VIDEO_FPS_MIN,
    VIDEO_READ_RETRY_LIMIT,
    VIDEO_TRUNCATION_RATIO,
)
from ai.pose.detector import PoseDetector
from ai.video.annotator import draw_hud, draw_person

# 직전에 끝난 rep의 판정 → 스켈레톤 색 (BGR)
_VERDICT_COLOR: dict[RepVerdict, tuple[int, int, int]] = {
    RepVerdict.CORRECT: (0, 200, 0),        # 초록
    RepVerdict.NEEDS_WORK: (0, 215, 255),   # 노랑
    RepVerdict.INCORRECT: (0, 0, 255),      # 빨강
}


def _detection_gate(report: Report, processed: int, with_person: int) -> None:
    """사람 검출률이 낮으면 결과를 신뢰하기 어렵다는 영상 수준 경고를 붙인다."""
    if processed <= 0:
        return
    ratio = with_person / processed
    if ratio < MIN_PERSON_RATIO:
        report.add_video_issue(Issue(
            rep_index=0, code="low_detection", severity=Severity.WARNING,
            message="영상에서 사람이 안정적으로 검출되지 않아 결과가 부정확할 수 있습니다. "
                    "전신이 나오도록 밝은 곳에서 다시 촬영해 주세요.",
            measured=round(ratio, 2), threshold=MIN_PERSON_RATIO,
        ))


def _decode_gate(report: Report, read_frames: int, declared_frames: int) -> None:
    """영상을 끝까지 못 읽고 중간에서 끊겼으면 경고를 붙인다.

    손상된 파일은 read()가 중간에서 False를 돌려주는데, 그대로 종료하면 뒤쪽
    구간이 통째로 빠진 채 '정상 리포트'가 나온다. 결과를 지어내지 않으려면
    '분석이 영상 전체를 못 봤다'는 사실 자체를 남겨야 한다.
    선언 프레임 수가 0/음수인 영상(스트림·메타데이터 없음)은 비교 자체가 불가능해 건너뛴다.
    """
    if declared_frames <= 0:
        return
    ratio = read_frames / declared_frames
    if ratio < VIDEO_TRUNCATION_RATIO:
        report.add_video_issue(Issue(
            rep_index=0, code="truncated_video", severity=Severity.WARNING,
            message=f"영상 파일이 손상되어 전체 {declared_frames}프레임 중 "
                    f"{read_frames}프레임까지만 읽었습니다. 뒷부분 동작은 횟수에 "
                    f"포함되지 않았으니 영상을 다시 올려 주세요.",
            measured=round(ratio, 2), threshold=VIDEO_TRUNCATION_RATIO,
        ))


def _inference_gate(report: Report, processed: int, failed: int) -> None:
    """프레임 단위 추론이 예외로 실패한 비율이 높으면 경고를 붙인다."""
    if processed <= 0 or failed <= 0:
        return
    ratio = failed / processed
    if ratio > MAX_DETECT_FAILURE_RATIO:
        report.add_video_issue(Issue(
            rep_index=0, code="inference_error", severity=Severity.WARNING,
            message=f"관절 검출이 {failed}프레임에서 실패해 그 구간은 분석에서 "
                    f"제외됐습니다. 결과가 부정확할 수 있습니다.",
            measured=round(ratio, 2), threshold=MAX_DETECT_FAILURE_RATIO,
        ))


def analyze_video(
    video_path: str | Path,
    exercise: str = "squat",
    *,
    save_annotated: bool = True,
    frame_stride: int = 1,
    detector: PoseDetector | None = None,
) -> Report:
    """영상 파일을 분석해 리포트를 반환한다.

    매개변수
    - video_path: 분석할 영상 경로
    - exercise: 운동 키 ("squat" 등). 등록된 것만 가능.
    - save_annotated: True면 관절을 그린 결과 영상을 data/output/에 저장.
    - frame_stride: N이면 N프레임마다 1장만 처리(속도↑, 정확도↓). 1=모든 프레임.
    - detector: 미리 만든 PoseDetector 재사용(서버에서 모델을 한 번만 로드하려고).
      직접 넘기면 운동별 가중치 선택(pose_model_for)을 건너뛰므로, 호출부가
      운동에 맞는 모델로 만들어 넘겨야 한다.

    반환: Report (report.to_dict() 로 JSON 직렬화 가능)
    """
    video_path = Path(video_path)
    if not video_path.exists():
        raise FileNotFoundError(f"영상을 찾을 수 없습니다: {video_path}")

    # 운동마다 가중치가 다르다(푸시업은 팔꿈치각 노이즈 때문에 s를 쓴다).
    detector = detector or PoseDetector(pose_model_for(exercise))
    detector.reset()  # 재사용 시 직전 영상의 사람 추적을 초기화

    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError(f"영상을 열 수 없습니다: {video_path}")

    # 메타데이터가 깨진 영상은 fps로 0·None뿐 아니라 1000 같은 쓰레기 값도 준다.
    # 그대로 쓰면 rep 시각(초)이 전부 틀어지므로 범위 밖이면 대체값을 쓴다.
    fps = cap.get(cv2.CAP_PROP_FPS) or 0.0
    if not (VIDEO_FPS_MIN <= fps <= VIDEO_FPS_MAX):
        fps = VIDEO_FPS_FALLBACK
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    # 손상 영상 조기 종료를 감지하려면 '몇 프레임짜리라고 선언했는지'가 필요하다.
    # 이 값 자체가 틀린 영상도 많으므로 경고 판단에만 쓰고 루프 제어에는 쓰지 않는다.
    declared_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)

    # fps를 넘겨야 분석기가 rep별 시각(초)을 계산할 수 있다.
    analyzer = create_analyzer(exercise, fps=fps)

    writer = None
    out_path: Path | None = None
    if save_annotated:
        out_path = OUTPUT_DIR / f"{video_path.stem}_annotated.mp4"
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        writer = cv2.VideoWriter(str(out_path), fourcc, fps / max(1, frame_stride), (width, height))

    frame_index = 0
    processed = 0
    with_person = 0
    skipped = 0        # 디코딩 실패로 건너뛴 프레임
    detect_failed = 0  # 추론이 예외로 죽은 프레임
    consecutive_read_failures = 0
    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                # 영상 끝인지 손상 프레임인지 read()만으로는 구분되지 않는다.
                # 몇 프레임 건너뛰며 재시도해 보고, 계속 실패하면 그때 끝으로 본다.
                consecutive_read_failures += 1
                if consecutive_read_failures > VIDEO_READ_RETRY_LIMIT:
                    # 재시도로 늘어난 인덱스를 되돌려 실제로 읽은 위치만 남긴다.
                    frame_index -= VIDEO_READ_RETRY_LIMIT
                    skipped -= VIDEO_READ_RETRY_LIMIT
                    break
                frame_index += 1
                skipped += 1
                continue
            consecutive_read_failures = 0

            if frame_index % frame_stride == 0:
                # 한 프레임의 추론 실패가 영상 전체 분석을 죽이지 않게 격리한다.
                # 실패 프레임은 '사람이 안 잡힌 프레임'과 같게 취급한다(아래 분석기가
                # 유실 구간으로 처리). 실패 사실은 따로 세어 리포트에 남긴다.
                try:
                    person = detector.detect(frame)
                except Exception:  # noqa: BLE001 - 추론 백엔드가 무엇을 던질지 알 수 없다
                    person = None
                    detect_failed += 1
                analyzer.update(person, frame_index)
                processed += 1
                if person is not None:
                    with_person += 1

                if writer is not None:
                    annotated = frame
                    if person is not None:
                        # 스켈레톤 색 = 직전에 끝난 rep의 판정색(첫 rep 전엔 기본색)
                        bone_color = None
                        last_rep = analyzer.report.rep_count
                        if last_rep > 0:
                            bone_color = _VERDICT_COLOR[analyzer.report.rep_verdict(last_rep)]
                        annotated = draw_person(frame, person, bone_color=bone_color)
                    # HUD는 cv2 폰트라 영어로 (한글은 깨짐)
                    annotated = draw_hud(annotated, [f"Exercise: {exercise}", *analyzer.hud_lines()])
                    writer.write(annotated)

            frame_index += 1
    finally:
        cap.release()
        if writer is not None:
            writer.release()

    report = analyzer.finalize()
    report.frames_processed = processed
    report.frames_with_person = with_person
    report.frames_skipped = skipped
    report.frames_detect_failed = detect_failed
    _decode_gate(report, frame_index, declared_frames)
    _inference_gate(report, processed, detect_failed)
    _detection_gate(report, processed, with_person)
    if out_path is not None:
        report.annotated_video_path = str(out_path)
    return report

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
    MIN_PERSON_RATIO,
    OUTPUT_DIR,
    VIDEO_FPS_FALLBACK,
    VIDEO_FPS_MAX,
    VIDEO_FPS_MIN,
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

    반환: Report (report.to_dict() 로 JSON 직렬화 가능)
    """
    video_path = Path(video_path)
    if not video_path.exists():
        raise FileNotFoundError(f"영상을 찾을 수 없습니다: {video_path}")

    detector = detector or PoseDetector()
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
    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                break

            if frame_index % frame_stride == 0:
                person = detector.detect(frame)
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
    _detection_gate(report, processed, with_person)
    if out_path is not None:
        report.annotated_video_path = str(out_path)
    return report

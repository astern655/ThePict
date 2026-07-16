"""AI 엔진의 공개 진입점.

백엔드 서버는 이 파일의 analyze_video() 하나만 호출하면 된다.
내부적으로 '프레임 읽기 → YOLO 관절검출 → 운동 분석 → (선택)주석영상 저장'을 엮는다.
"""
from __future__ import annotations

from pathlib import Path

import cv2

from ai.analysis.exercises import create_analyzer
from ai.analysis.feedback import Report
from ai.config import OUTPUT_DIR
from ai.pose.detector import PoseDetector
from ai.video.annotator import draw_hud, draw_person


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
    analyzer = create_analyzer(exercise)

    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError(f"영상을 열 수 없습니다: {video_path}")

    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

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
                        annotated = draw_person(frame, person)
                    # HUD는 cv2 폰트라 영어로 (한글은 깨짐)
                    annotated = draw_hud(annotated, [
                        f"Exercise: {exercise}",
                        f"Reps: {analyzer.report.rep_count}",
                    ])
                    writer.write(annotated)

            frame_index += 1
    finally:
        cap.release()
        if writer is not None:
            writer.release()

    report = analyzer.finalize()
    report.frames_processed = processed
    report.frames_with_person = with_person
    if out_path is not None:
        report.annotated_video_path = str(out_path)
    return report

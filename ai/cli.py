"""AI 엔진 단독 실행 CLI.

서버·프론트 없이 터미널에서 AI만 바로 시험한다.

사용:
    python -m ai.cli <영상경로> [--exercise squat] [--stride 2] [--no-video]
"""
from __future__ import annotations

import argparse
import json
import sys

from ai.analysis.exercises import available_exercises
from ai.engine import analyze_video


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="운동 자세 분석 AI 엔진")
    parser.add_argument("video", help="분석할 영상 파일 경로")
    parser.add_argument("--exercise", default="squat",
                        help=f"운동 종류 (기본: squat). 가능: {', '.join(available_exercises())}")
    parser.add_argument("--stride", type=int, default=1,
                        help="N프레임마다 1장 처리(속도↑). 기본 1")
    parser.add_argument("--no-video", action="store_true",
                        help="주석 영상 저장 안 함(리포트만)")
    parser.add_argument("--json", action="store_true", help="결과를 JSON으로 출력")
    args = parser.parse_args(argv)

    report = analyze_video(
        args.video,
        exercise=args.exercise,
        save_annotated=not args.no_video,
        frame_stride=args.stride,
    )

    if args.json:
        print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
    else:
        print("\n".join(report.summary_lines()))
        print(f"\n처리 프레임: {report.frames_processed} "
              f"(사람 검출 {report.frames_with_person})")
        if report.annotated_video_path:
            print(f"주석 영상: {report.annotated_video_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

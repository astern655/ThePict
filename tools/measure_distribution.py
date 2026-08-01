"""실영상에서 rep별 측정값 분포와 측면 검증 표본을 뽑는다 (운동 공용).

임계값을 데이터로 정하려면 두 가지가 먼저 필요하다.

1. **rep별 원시 측정값** — 최저점 관절각과 운동별 두 번째 지표(스쿼트=상체·정강이
   기울기, 푸시업=몸통 일직선 이탈각). 판정(결함 여부)이 아니라 숫자 자체를 봐야
   정상 분포의 상단이 보인다. (docs/SQUAT_TUNING.md §5-2, docs/PUSHUP_TUNING.md §4)
2. **측면 자동검증이 실제로 작동하는지** — `side_view_ratio`는 좌우 어깨가 둘 다
   보일 때만 계산된다. 표본이 `SIDE_VIEW_MIN_SAMPLES`에 못 미치면 검사가 조용히
   생략되므로, 몇 개나 쌓이는지 세어 봐야 검사가 살아 있는지 알 수 있다.

프레임을 하나도 건너뛰지 않는다. 최저점 프레임을 놓치면 측정값이 통째로 틀어진다.

실행:
    py -m tools.measure_distribution                          # data/videos/squat*.mp4
    py -m tools.measure_distribution --exercise pushup
    py -m tools.measure_distribution data/videos/squat_001.mp4 --json out.json
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path

import cv2

from ai.analysis.exercises import create_analyzer
from ai.analysis.landmarks import side_view_ratio
from ai.config import (
    SIDE_VIEW_MIN_SAMPLES,
    SIDE_VIEW_RATIO_MAX,
    VIDEO_FPS_FALLBACK,
    VIDEO_FPS_MAX,
    VIDEO_FPS_MIN,
    pose_model_for,
)
from ai.pose.detector import PoseDetector

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DIR = PROJECT_ROOT / "data" / "videos"

# 운동별로 볼 측정값(표시 이름, RepRecord 필드). 첫 항목은 기준 관절각이다.
# 분포 요약도 이 표를 따라가므로 새 운동은 여기 한 줄만 늘리면 된다.
COLUMNS: dict[str, list[tuple[str, str]]] = {
    "squat": [
        ("무릎각", "bottom_angle"),
        ("대퇴각", "bottom_femur_elevation"),
        ("구간위치", "bottom_hip_in_span"),
        ("상체", "bottom_torso_incline"),
        ("정강이", "bottom_shin_incline"),
        ("차이", "bottom_torso_shin_diff"),
    ],
    "pushup": [
        ("팔꿈치각", "bottom_angle"),
        ("몸통이탈", "bottom_body_line_dev"),
    ],
}


def measure(video: Path, exercise: str, detector: PoseDetector) -> dict:
    """영상 하나를 분석해 rep별 측정값과 측면 표본 통계를 모은다.

    engine.analyze_video를 쓰지 않는 이유: 측면 비율 표본은 리포트에 실리지 않아
    분석기 내부를 직접 봐야 한다. 판정 로직은 같은 분석기를 그대로 쓴다.
    """
    cap = cv2.VideoCapture(str(video))
    if not cap.isOpened():
        raise RuntimeError(f"영상을 열 수 없습니다: {video}")

    fps = cap.get(cv2.CAP_PROP_FPS) or 0.0
    if not (VIDEO_FPS_MIN <= fps <= VIDEO_FPS_MAX):
        fps = VIDEO_FPS_FALLBACK

    detector.reset()
    analyzer = create_analyzer(exercise, fps=fps)
    ratios: list[float] = []  # 어깨 둘 다 보인 프레임에서만 쌓인다
    # 평활화 '전' 기준 관절각의 프레임 간 변화량. 이 값이 크면 임계값을 아무리
    # 잘 잡아도 판정이 흔들린다 — 최저점을 min()으로 잡기 때문에 특히 그렇다.
    jitter: list[float] = []
    prev_angle: float | None = None
    prev_frame: int | None = None
    frames = with_person = both_shoulders = 0

    frame_index = 0
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        try:
            person = detector.detect(frame)
        except Exception:  # noqa: BLE001 - 추론 백엔드가 무엇을 던질지 알 수 없다
            person = None
        frames += 1
        if person is not None:
            with_person += 1
            ratio = side_view_ratio(person)
            if ratio is not None:
                both_shoulders += 1
                ratios.append(ratio)
            raw = analyzer.measure_angle(person)
            if raw is not None:
                # 바로 이전 프레임과만 비교한다. 유실 구간을 건너뛴 값끼리
                # 비교하면 노이즈가 아니라 실제 움직임을 재게 된다.
                if prev_angle is not None and prev_frame == frame_index - 1:
                    jitter.append(abs(raw - prev_angle))
                prev_angle, prev_frame = raw, frame_index
        analyzer.update(person, frame_index)
        frame_index += 1
    cap.release()

    report = analyzer.finalize()
    columns = COLUMNS[exercise]
    # [스쿼트] 완전히 선 자세의 대퇴 거상각(이론값 +90°). 90°와의 차이가
    # 카메라 기울기 + 관절점 오프셋 → 기립 캘리브레이션 후보 신호다.
    standing = getattr(analyzer, "_standing_femurs", [])
    reps = [
        {
            "rep_index": r.rep_index,
            "verdict": report.rep_verdict(r.rep_index).value,
            "bottom_sec": r.bottom_sec,
            **{field: getattr(r, field) for _label, field in columns},
        }
        for r in report.reps
    ]
    return {
        "exercise": exercise,
        "video": video.name,
        "fps": round(fps, 2),
        "frames": frames,
        "person_ratio": round(with_person / frames, 3) if frames else 0.0,
        "rep_count": report.rep_count,
        "partial_rep_count": report.partial_rep_count,
        "video_codes": [i.code for i in report.video_issues],
        "view_samples": len(ratios),
        "view_sample_ratio": round(both_shoulders / with_person, 3) if with_person else 0.0,
        "view_median": round(statistics.median(ratios), 3) if ratios else None,
        "view_min": round(min(ratios), 3) if ratios else None,
        "view_max": round(max(ratios), 3) if ratios else None,
        "side_check_ran": len(ratios) >= SIDE_VIEW_MIN_SAMPLES,
        "angle_jitter_median": round(statistics.median(jitter), 2) if jitter else None,
        "angle_jitter_p95": (
            round(sorted(jitter)[int(len(jitter) * 0.95)], 2) if len(jitter) >= 20 else None
        ),
        "angle_jitter_max": round(max(jitter), 2) if jitter else None,
        "standing_femur_samples": len(standing),
        "standing_femur_median": (
            round(statistics.median(standing), 1) if standing else None
        ),
        "standing_femur_p10": (
            round(sorted(standing)[int(len(standing) * 0.10)], 1)
            if len(standing) >= 10 else None
        ),
        "reps": reps,
    }


def _fmt(value: float | None, width: int = 7) -> str:
    return f"{value:>{width}.1f}" if value is not None else f"{'—':>{width}}"


def print_result(result: dict) -> None:
    columns = COLUMNS[result["exercise"]]
    print(f"\n■ {result['video']}  fps={result['fps']}  프레임={result['frames']}  "
          f"검출률={result['person_ratio']}")
    print(f"  rep {result['rep_count']}회 / 부분 {result['partial_rep_count']}회"
          f"  영상코드={result['video_codes'] or '없음'}")

    ran = "검사 수행" if result["side_check_ran"] else f"검사 생략(표본<{SIDE_VIEW_MIN_SAMPLES})"
    print(f"  측면 표본 {result['view_samples']}개"
          f"(사람 검출 프레임의 {result['view_sample_ratio']:.0%}) → {ran}"
          f"  중앙값={result['view_median']} (기준 {SIDE_VIEW_RATIO_MAX} 이하)"
          f"  범위={result['view_min']}~{result['view_max']}")

    # 기준 관절각의 프레임 간 흔들림. 최저점을 min()으로 잡으므로, 이 값이 크면
    # 깊이가 실제보다 깊게 기록된다(노이즈의 최저치를 집는다).
    print(f"  {columns[0][0]} 프레임 간 변화: 중앙 {result['angle_jitter_median']}°"
          f" / p95 {result['angle_jitter_p95']}° / 최대 {result['angle_jitter_max']}°")

    if result.get("standing_femur_median") is not None:
        print(f"  기립 대퇴 거상각: 중앙 {result['standing_femur_median']}°"
              f" / p10 {result['standing_femur_p10']}°"
              f" (표본 {result['standing_femur_samples']}개, 이론값 90°)")

    if not result["reps"]:
        return
    header = "   rep  판정        " + "".join(f"{label:>8}" for label, _f in columns)
    print(header + "   최저점(초)")
    for r in result["reps"]:
        sec = f"{r['bottom_sec']:.2f}" if r["bottom_sec"] is not None else "—"
        cells = "".join(_fmt(r[field], 8) for _label, field in columns)
        print(f"   {r['rep_index']:>3}  {r['verdict']:<12}{cells}   {sec:>8}")


def print_summary(results: list[dict], exercise: str) -> None:
    reps = [r for res in results for r in res["reps"]]
    if not reps:
        print("\nrep이 하나도 잡히지 않아 분포를 낼 수 없습니다.")
        return

    print("\n" + "=" * 72)
    print(f"[{exercise}] 전체 {len(results)}개 영상 · rep {len(reps)}개 분포")
    for label, field in COLUMNS[exercise]:
        values = [r[field] for r in reps if r[field] is not None]
        if not values:
            print(f"  {label}: 측정값 없음")
            continue
        print(f"  {label}: 최소 {min(values):.1f} / 중앙 {statistics.median(values):.1f} / "
              f"최대 {max(values):.1f}  (표본 {len(values)}개)")

    dead = [res["video"] for res in results if not res["side_check_ran"]]
    if dead:
        print(f"  ⚠️ 측면 검사가 생략된 영상 {len(dead)}개: {', '.join(dead)}")
        print("     표본이 계속 모자라면 이 검사는 사실상 죽어 있는 것이다"
              "(docs/SQUAT_TUNING.md §4).")


def main() -> int:
    parser = argparse.ArgumentParser(description="실영상 측정값 분포 / 측면 검증 표본 계측")
    parser.add_argument("videos", nargs="*",
                        help="분석할 영상(생략하면 data/videos/<운동>*.mp4 전부)")
    parser.add_argument("--exercise", default="squat", choices=sorted(COLUMNS),
                        help="분석할 운동 (기본: squat)")
    parser.add_argument("--json", dest="json_path", help="결과를 JSON으로 저장할 경로")
    parser.add_argument("--model", default=None,
                        help="YOLO pose 가중치 재정의(모델 크기 비교 실험용, 예: yolo11s-pose.pt)")
    args = parser.parse_args()

    paths = [Path(v) for v in args.videos] or sorted(DEFAULT_DIR.glob(f"{args.exercise}*.mp4"))
    if not paths:
        print(f"분석할 영상이 없습니다: {DEFAULT_DIR}\\{args.exercise}*.mp4")
        return 1

    # 모델은 한 번만 로드해 재사용. 기본은 운동별 가중치, --model로 재정의 가능.
    detector = PoseDetector(args.model or pose_model_for(args.exercise))
    results = []
    for path in paths:
        if not path.exists():
            print(f"건너뜀(파일 없음): {path}")
            continue
        result = measure(path, args.exercise, detector)
        results.append(result)
        print_result(result)

    print_summary(results, args.exercise)
    if args.json_path:
        Path(args.json_path).write_text(
            json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"\nJSON 저장: {args.json_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

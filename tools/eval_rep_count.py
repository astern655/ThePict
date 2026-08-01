"""반복 횟수 정답률 평가 (운동 공용).

`validate_labels.py`는 rep별 자세 코드까지 갖춘 완전한 라벨을 요구한다. 하지만
"몇 회인가"만 맞히는지 보려면 그만큼의 라벨이 필요 없고, 자세 라벨을 만들 수 없는
외부 영상도 횟수는 셀 수 있다. 그래서 횟수 전용 평가를 따로 둔다.

라벨 파일 형식 (`data/<운동>_rep_labels.json`):

    {
      "notes": "정답을 어떻게 셌는지 적어 둔다",
      "clips": {"clip_4964649": 3, "clip_6022762": 3}
    }

키는 `data/videos/<운동>_eval/` 안의 파일 이름(확장자 제외)이다.

> ⚠️ **정답을 만드는 방법이 중요하다.** 튜닝 대상이 기준 관절각(푸시업=팔꿈치각)이므로
> 그 각도로 정답을 만들면 순환 논리가 된다. 팔꿈치와 무관한 신호
> (손 대비 어깨 높이)를 그려 사람이 세는 방식을 썼다. docs/PUSHUP_TUNING.md §7-0

실행:
    py -m tools.eval_rep_count --exercise pushup
    py -m tools.eval_rep_count --exercise pushup --json data/output/pushup_rep_eval.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import cv2

from ai.analysis.exercises import create_analyzer
from ai.config import (
    VIDEO_FPS_FALLBACK,
    VIDEO_FPS_MAX,
    VIDEO_FPS_MIN,
    pose_model_for,
)
from ai.pose.detector import PoseDetector

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def analyze(video: Path, exercise: str, detector: PoseDetector) -> tuple[int, list[str]]:
    cap = cv2.VideoCapture(str(video))
    if not cap.isOpened():
        raise RuntimeError(f"영상을 열 수 없습니다: {video}")
    fps = cap.get(cv2.CAP_PROP_FPS) or 0.0
    if not (VIDEO_FPS_MIN <= fps <= VIDEO_FPS_MAX):
        fps = VIDEO_FPS_FALLBACK

    detector.reset()
    analyzer = create_analyzer(exercise, fps=fps)
    index = 0
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        try:
            person = detector.detect(frame)
        except Exception:  # noqa: BLE001 - 추론 백엔드가 무엇을 던질지 알 수 없다
            person = None
        analyzer.update(person, index)
        index += 1
    cap.release()
    report = analyzer.finalize()
    return report.rep_count, [i.code for i in report.video_issues]


def main() -> int:
    parser = argparse.ArgumentParser(description="반복 횟수 정답률 평가")
    parser.add_argument("--exercise", default="pushup", help="운동 키 (기본: pushup)")
    parser.add_argument("--labels", default=None,
                        help="라벨 JSON (기본: data/<운동>_rep_labels.json)")
    parser.add_argument("--videos", default=None,
                        help="영상 폴더 (기본: data/videos/<운동>_eval)")
    parser.add_argument("--json", dest="json_path", help="결과 JSON 저장 경로")
    args = parser.parse_args()

    labels_path = PROJECT_ROOT / (args.labels or f"data/{args.exercise}_rep_labels.json")
    if not labels_path.exists():
        print(f"라벨 파일이 없습니다: {labels_path}")
        return 2
    label_doc = json.loads(labels_path.read_text(encoding="utf-8"))
    gt: dict[str, int] = label_doc["clips"]

    videos_dir = PROJECT_ROOT / (args.videos or f"data/videos/{args.exercise}_eval")
    detector = PoseDetector(pose_model_for(args.exercise))

    rows, missing = [], []
    error = exact = obo = 0
    for name in sorted(gt):
        path = next((p for p in videos_dir.glob(f"{name}.*")
                     if p.suffix.lower() in (".mp4", ".webm", ".mov")), None)
        if path is None:
            missing.append(name)
            continue
        predicted, codes = analyze(path, args.exercise, detector)
        diff = abs(predicted - gt[name])
        error += diff
        exact += diff == 0
        obo += diff <= 1
        rows.append({"clip": name, "predicted": predicted, "truth": gt[name],
                     "video_codes": codes})
        print(f"  {'OK ' if diff == 0 else 'MISS'} {name:20} 예측 {predicted:2d} / 정답 "
              f"{gt[name]:2d}   {codes if codes else ''}")

    if not rows:
        print("평가할 영상이 없습니다.")
        return 2

    total = sum(gt[r["clip"]] for r in rows)
    summary = {
        "exercise": args.exercise,
        "clips": len(rows),
        "truth_reps": total,
        "rep_accuracy": round(1 - error / total, 4) if total else None,
        "exact_clip_rate": round(exact / len(rows), 4),
        "within_one_rate": round(obo / len(rows), 4),
        "total_error": error,
    }
    print(f"\n영상 {len(rows)}편 · 정답 {total}회")
    print(f"  rep 단위 정답률    {summary['rep_accuracy']:.1%}  (오차 {error}회)")
    print(f"  영상 단위 정확 일치 {exact}/{len(rows)} ({summary['exact_clip_rate']:.0%})")
    print(f"  영상 단위 ±1 이내   {obo}/{len(rows)} ({summary['within_one_rate']:.0%})")
    if missing:
        print(f"  ⚠️ 영상이 없어 건너뜀 {len(missing)}편: {', '.join(missing)}")

    if args.json_path:
        Path(args.json_path).write_text(
            json.dumps({"summary": summary, "rows": rows}, ensure_ascii=False, indent=2),
            encoding="utf-8")
        print(f"\nJSON 저장: {args.json_path}")
    return 0 if error == 0 and not missing else 1


if __name__ == "__main__":
    sys.exit(main())

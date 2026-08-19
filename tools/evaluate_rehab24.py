"""REHAB24-6 Ex3(테이블 인클라인 푸시업)으로 푸시업 판정을 외부 검증한다.

데이터: REHAB24-6 (Zenodo 13305826, CC BY-NC 4.0). Ex3는 측면(profile) 카메라
영상 10편, 물리치료사 감수 세그먼트 107 rep(정상 52 / 결함 55)이다.

라벨은 **이진 정오뿐**이고 결함 종류(깊이/몸통/기타)는 구분돼 있지 않다.
따라서 여기서 재는 것은:
  - rep 세그먼트 매칭률 (엔진 rep ↔ 전문가 세그먼트, 프레임 겹침 기준)
  - '엔진이 어떤 결함 신호든 낸 rep' 의 이진 정오 대비 재현율/특이도
  - 깊이 축 단독 신호의 재현율/특이도 (결함이 깊이가 아닐 수 있으므로 하한)
결함 종류가 섞여 있으므로 재현율은 '우리 규칙이 커버하는 결함 비율'의
추정이지 깊이 규칙 자체의 정확도가 아니다 — 해석 주의.

사용:
    py -3 -m tools.evaluate_rehab24
    (data/external/rehab24/ 아래 Segmentation.csv와 Ex3 영상 필요)
"""
from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
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

DEPTH_DEFECT_CODES = {"shallow_depth", "very_shallow_depth"}
BODY_DEFECT_CODES = {"body_line_break", "excessive_body_line_break"}


def load_segments(csv_path: Path) -> dict[str, list[dict]]:
    segments: dict[str, list[dict]] = defaultdict(list)
    with csv_path.open(encoding="utf-8") as fh:
        for row in csv.DictReader(fh, delimiter=";"):
            if row["exercise_id"] != "3":
                continue
            segments[row["video_id"]].append({
                "rep": int(row["repetition_number"]),
                "start": int(row["first_frame"]),
                "end": int(row["last_frame"]),
                "person": row["person_id"],
                "correct": row["correctness"] == "1",
            })
    return segments


def analyze_video(video: Path, detector: PoseDetector):
    cap = cv2.VideoCapture(str(video))
    fps = cap.get(cv2.CAP_PROP_FPS) or 0.0
    if not (VIDEO_FPS_MIN <= fps <= VIDEO_FPS_MAX):
        fps = VIDEO_FPS_FALLBACK
    detector.reset()
    analyzer = create_analyzer("pushup", fps=fps)
    idx = 0
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        try:
            person = detector.detect(frame)
        except Exception:
            person = None
        analyzer.update(person, idx)
        idx += 1
    cap.release()
    return analyzer.finalize(), idx


def match_reps(report, segments: list[dict]) -> list[dict]:
    """전문가 세그먼트마다 프레임 겹침이 가장 큰 엔진 rep을 짝짓는다."""
    rows = []
    used = set()
    for seg in sorted(segments, key=lambda s: s["start"]):
        best, best_overlap = None, 0
        for rep in report.reps:
            if rep.rep_index in used:
                continue
            overlap = min(seg["end"], rep.end_frame) - max(seg["start"], rep.start_frame)
            if overlap > best_overlap:
                best, best_overlap = rep, overlap
        entry = {**seg, "matched": best is not None}
        if best is not None:
            used.add(best.rep_index)
            issues = report.issues_for_rep(best.rep_index)
            codes = {i.code for i in issues}
            entry.update({
                "engine_rep": best.rep_index,
                "bottom_angle": best.bottom_angle,
                "body_line_dev": best.bottom_body_line_dev,
                "top_body_line_dev": best.top_body_line_dev,
                "depth_flag": bool(codes & DEPTH_DEFECT_CODES),
                "body_flag": bool(codes & BODY_DEFECT_CODES),
                "any_flag": bool(codes & (DEPTH_DEFECT_CODES | BODY_DEFECT_CODES)),
            })
        rows.append(entry)
    return rows


def confusion(rows: list[dict], key: str) -> dict:
    matched = [r for r in rows if r["matched"]]
    tp = sum(not r["correct"] and r[key] for r in matched)
    tn = sum(r["correct"] and not r[key] for r in matched)
    fp = sum(r["correct"] and r[key] for r in matched)
    fn = sum(not r["correct"] and not r[key] for r in matched)
    n = len(matched)

    def ratio(a, b):
        return round(a / b, 4) if b else 0.0

    rec, spec = ratio(tp, tp + fn), ratio(tn, tn + fp)
    return {
        "matched": n, "tp": tp, "tn": tn, "fp": fp, "fn": fn,
        "accuracy": ratio(tp + tn, n), "recall": rec, "specificity": spec,
        "f1": ratio(2 * tp, 2 * tp + fp + fn),
        "balanced_accuracy": round((rec + spec) / 2, 4),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="REHAB24-6 Ex3 푸시업 외부 검증")
    parser.add_argument("--data-root", type=Path, default=Path("data/external/rehab24"))
    parser.add_argument("--output", type=Path,
                        default=Path("data/output/rehab24_evaluation.json"))
    parser.add_argument("--model", default=None)
    args = parser.parse_args()

    segments = load_segments(args.data_root / "Segmentation.csv")
    detector = PoseDetector(args.model or pose_model_for("pushup"))

    all_rows = []
    per_video = {}
    for video_id, segs in sorted(segments.items()):
        matches = sorted(args.data_root.glob(f"**/*{video_id}*.mp4")) + \
            sorted(args.data_root.glob(f"**/*{video_id}*.avi"))
        if not matches:
            print(f"{video_id}: 영상 파일 없음 — 건너뜀")
            continue
        video = matches[0]
        report, frames = analyze_video(video, detector)
        rows = match_reps(report, segs)
        all_rows.extend(rows)
        per_video[video_id] = {
            "file": video.name,
            "frames": frames,
            "engine_reps": report.rep_count,
            "expert_reps": len(segs),
            "matched": sum(r["matched"] for r in rows),
            "video_codes": [i.code for i in report.video_issues],
        }
        print(f"{video_id}: 엔진 {report.rep_count} / 전문가 {len(segs)} / "
              f"매칭 {per_video[video_id]['matched']}")

    matched = [r for r in all_rows if r["matched"]]
    result = {
        "dataset": {
            "name": "REHAB24-6 Ex3 (table push-ups)",
            "source": "Zenodo 13305826",
            "license": "CC BY-NC 4.0 — 비상업 조건. 임계값 '검증'에만 쓰고 데이터 재배포 금지",
            "expert_reps": len(all_rows),
            "matched_reps": len(matched),
            "positives_incorrect": sum(not r["correct"] for r in matched),
        },
        "caveat": "정오 라벨은 이진이며 결함 종류(깊이/몸통/기타) 구분이 없다. "
                  "재현율은 '우리 규칙이 커버하는 결함 비율'의 추정이다.",
        "any_signal_vs_incorrect": confusion(all_rows, "any_flag"),
        "depth_only_vs_incorrect": confusion(all_rows, "depth_flag"),
        "body_only_vs_incorrect": confusion(all_rows, "body_flag"),
        "per_video": per_video,
        "reps": [
            {k: v for k, v in r.items()} for r in all_rows
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=1),
                           encoding="utf-8")
    summary = {k: v for k, v in result.items() if k not in ("reps", "per_video")}
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    print(f"전체 리포트: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""REHAB24-6 Ex6(스쿼트)으로 스쿼트 파이프라인을 **홀드아웃** 검증한다.

이 데이터는 스쿼트 임계값 결정에 전혀 쓰이지 않았다(깊이 임계값은 LLM-FMS,
오탐 제약은 로컬 영상). 따라서 여기 성적은 낙관 편향 없는 최종 시험이다.
스쿼트 반복 카운트의 외부 검증은 이것이 처음이다(기존 근거는 로컬 5편 14 rep).

카메라 기하: 두 카메라가 수직 배치라 cam17이 front인 rep 구간에서는
cam18(-transposed 영상)이 측면(profile)이 된다. 영상 하나에 정면 세트와
대각 세트가 섞여 있으므로:
  - rep 카운트: 영상 전체 세그먼트 수와 비교(엔진은 전체를 본다)
  - 자세 판정 지표: cam17_orientation == 'front'(= cam18 측면) rep만 집계

라벨은 이진 정오뿐이고 결함 종류(깊이/상체/기타) 구분이 없다 — 재현율은
'우리 규칙이 커버하는 결함 비율'의 추정이다(푸시업 Ex3와 동일한 주의).

사용: py -3 -m tools.evaluate_rehab24_squat
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

DEPTH_CODES = {"shallow_depth", "very_shallow_depth"}
BORDERLINE = {"borderline_depth"}
TORSO_CODES = {"torso_lean", "excessive_torso_lean"}


def load_segments(csv_path: Path) -> dict[str, list[dict]]:
    segments: dict[str, list[dict]] = defaultdict(list)
    with csv_path.open(encoding="utf-8") as fh:
        for row in csv.DictReader(fh, delimiter=";"):
            if row["exercise_id"] != "6":
                continue
            segments[row["video_id"]].append({
                "rep": int(row["repetition_number"]),
                "start": int(row["first_frame"]),
                "end": int(row["last_frame"]),
                "cam17": row["cam17_orientation"],
                "correct": row["correctness"] == "1",
            })
    return segments


def analyze_video(video: Path, detector: PoseDetector):
    cap = cv2.VideoCapture(str(video))
    fps = cap.get(cv2.CAP_PROP_FPS) or 0.0
    if not (VIDEO_FPS_MIN <= fps <= VIDEO_FPS_MAX):
        fps = VIDEO_FPS_FALLBACK
    detector.reset()
    analyzer = create_analyzer("squat", fps=fps)
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
    rows = []
    used = set()
    for seg in sorted(segments, key=lambda s: s["start"]):
        best, best_ov = None, 0
        for rep in report.reps:
            if rep.rep_index in used:
                continue
            ov = min(seg["end"], rep.end_frame) - max(seg["start"], rep.start_frame)
            if ov > best_ov:
                best, best_ov = rep, ov
        entry = {**seg, "matched": best is not None}
        if best is not None:
            used.add(best.rep_index)
            codes = {i.code for i in report.issues_for_rep(best.rep_index)}
            entry.update({
                "engine_rep": best.rep_index,
                "bottom_femur": best.bottom_femur_elevation,
                "torso_shin_diff": best.bottom_torso_shin_diff,
                "depth_flag": bool(codes & DEPTH_CODES),
                "detect_flag": bool(codes & (DEPTH_CODES | BORDERLINE | TORSO_CODES)),
                "torso_flag": bool(codes & TORSO_CODES),
                "warn_flag": bool(codes & (DEPTH_CODES | TORSO_CODES)),
            })
        rows.append(entry)
    return rows


def confusion(rows: list[dict], key: str) -> dict:
    m = [r for r in rows if r["matched"]]
    tp = sum(not r["correct"] and r[key] for r in m)
    tn = sum(r["correct"] and not r[key] for r in m)
    fp = sum(r["correct"] and r[key] for r in m)
    fn = sum(not r["correct"] and not r[key] for r in m)

    def ratio(a, b):
        return round(a / b, 4) if b else 0.0

    rec, spec = ratio(tp, tp + fn), ratio(tn, tn + fp)
    return {
        "matched": len(m), "tp": tp, "tn": tn, "fp": fp, "fn": fn,
        "accuracy": ratio(tp + tn, len(m)), "recall": rec, "specificity": spec,
        "balanced_accuracy": round((rec + spec) / 2, 4),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="REHAB24-6 Ex6 스쿼트 홀드아웃 검증")
    parser.add_argument("--data-root", type=Path, default=Path("data/external/rehab24"))
    parser.add_argument("--output", type=Path,
                        default=Path("data/output/rehab24_squat_evaluation.json"))
    parser.add_argument("--model", default=None)
    args = parser.parse_args()

    segments = load_segments(args.data_root / "Segmentation.csv")
    detector = PoseDetector(args.model or pose_model_for("squat"))

    all_rows, per_video = [], {}
    for video_id, segs in sorted(segments.items()):
        matches = sorted(args.data_root.glob(f"Ex6/*{video_id}*Camera18*.mp4"))
        if not matches:
            print(f"{video_id}: 영상 없음 — 건너뜀")
            continue
        report, frames = analyze_video(matches[0], detector)
        rows = match_reps(report, segs)
        all_rows.extend(rows)
        per_video[video_id] = {
            "frames": frames,
            "engine_reps": report.rep_count,
            "expert_reps": len(segs),
            "matched": sum(r["matched"] for r in rows),
            "video_codes": [i.code for i in report.video_issues],
        }
        print(f"{video_id}: 엔진 {report.rep_count} / 전문가 {len(segs)} / "
              f"매칭 {per_video[video_id]['matched']}")

    side = [r for r in all_rows if r["cam17"] == "front"]  # cam18 = 측면
    result = {
        "dataset": {
            "name": "REHAB24-6 Ex6 (squats, Camera18 side subset)",
            "source": "Zenodo 13305826",
            "license": "CC BY-NC 4.0 — 검증 전용",
            "holdout": "스쿼트 임계값 결정에 이 데이터는 일절 사용되지 않음",
            "expert_reps_total": len(all_rows),
            "side_view_reps": len(side),
            "side_incorrect": sum(not r["correct"] for r in side),
        },
        "rep_count": {
            "videos": len(per_video),
            "exact_videos": sum(1 for v in per_video.values()
                                if v["engine_reps"] == v["expert_reps"]),
            "abs_err": sum(abs(v["engine_reps"] - v["expert_reps"])
                           for v in per_video.values()),
            "total_expert": sum(v["expert_reps"] for v in per_video.values()),
            "match_rate": round(sum(v["matched"] for v in per_video.values())
                                / len(all_rows), 4) if all_rows else 0,
        },
        "side_view_detection": {
            "any_signal(경계 포함)": confusion(side, "detect_flag"),
            "warning_이상": confusion(side, "warn_flag"),
            "depth_only": confusion(side, "depth_flag"),
            "torso_only": confusion(side, "torso_flag"),
        },
        "per_video": per_video,
        "reps": all_rows,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=1),
                           encoding="utf-8")
    print(json.dumps({k: v for k, v in result.items() if k != "reps"},
                     ensure_ascii=False, indent=1))
    print(f"전체 리포트: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""LLM-FMS 딥 스쿼트 핵심 프레임으로 스쿼트 피드백 임계값을 검증한다.

LLM-FMS의 정답을 현재 서비스 피드백에 다음처럼 대응한다.

* Hip height == Higher  -> 깊이 부족
* Trunk-calf == Not parallel -> 상체 숙임

데이터셋의 FMS 총점은 손목 위치까지 반영하므로 이 도구는 총점을 예측하지 않는다.
또한 핵심 프레임 데이터이므로 반복 횟수 정확도도 평가하지 않는다.

사용:
    py -3 -m tools.evaluate_llm_fms
    py -3 -m tools.evaluate_llm_fms --data-root data/external/llm_fms
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable, Iterable

import cv2
import numpy as np

from ai.analysis.exercises.squat import (
    _FEMURS,
    _mid_knee_angle,
    _shin_incline,
    _torso_lean,
    check_depth,
    check_depth_femur,
    check_torso,
)
from ai.analysis.landmarks import mean_femur_elevation
from ai.config import (
    SQUAT_FEMUR_ELEVATION_WARN,
    SQUAT_TORSO_LEAN_HARD_MAX,
    SQUAT_TORSO_SHIN_DIFF_WARN,
)
from ai.pose.detector import PoseDetector
from ai.pose.keypoints import KP

DATASET_DOI = "10.6084/m9.figshare.c.7601630.v1"
DATASET_LICENSE = "CC BY 4.0"
DEFAULT_ACTIONS = ("m01", "m02")
SUBJECT_RE = re.compile(r"_s(?P<subject>\d+)_")


@dataclass
class Sample:
    image: str
    action: str
    subject: str
    score: int
    truth_depth_issue: bool
    truth_torso_issue: bool
    hip_answer: str
    trunk_answer: str
    detected: bool
    knee_angle: float | None = None
    femur_elevation: float | None = None  # 대퇴 거상각(도) — 현재 깊이 1차 지표
    torso_incline: float | None = None
    shin_incline: float | None = None
    torso_shin_diff: float | None = None
    hip_knee_vertical_offset: float | None = None
    hip_knee_vertical_ratio: float | None = None
    predicted_depth_issue: bool | None = None
    predicted_depth_code: str | None = None
    predicted_torso_issue: bool | None = None
    predicted_torso_code: str | None = None


def _read_image(path: Path) -> np.ndarray | None:
    """Windows의 비 ASCII 경로에서도 동작하는 OpenCV 이미지 로더."""
    try:
        encoded = np.fromfile(path, dtype=np.uint8)
    except OSError:
        return None
    if encoded.size == 0:
        return None
    return cv2.imdecode(encoded, cv2.IMREAD_COLOR)


def _safe_round(value: float | None) -> float | None:
    if value is None or not math.isfinite(value):
        return None
    return round(value, 3)


def load_sample(label_path: Path, image_dir: Path, detector: PoseDetector) -> Sample:
    label = json.loads(label_path.read_text(encoding="utf-8"))
    subject_match = SUBJECT_RE.search(label["picName"])
    if subject_match is None:
        raise ValueError(f"피험자 ID를 읽을 수 없는 파일명: {label['picName']}")

    trunk_answer = label["ruleResults"]["r01"]["ruleAnswer"]
    hip_answer = label["ruleResults"]["r02"]["ruleAnswer"]
    sample = Sample(
        image=label["picName"],
        action=label_path.parent.name,
        subject=subject_match.group("subject"),
        score=int(label["score"]),
        truth_depth_issue=hip_answer == "Higher",
        truth_torso_issue=trunk_answer == "Not parallel",
        hip_answer=hip_answer,
        trunk_answer=trunk_answer,
        detected=False,
    )

    frame = _read_image(image_dir / label["picName"])
    if frame is None:
        return sample
    detector.reset()
    person = detector.detect(frame)
    if person is None:
        return sample

    knee = _mid_knee_angle(person)
    femur = mean_femur_elevation(person, _FEMURS)
    torso = _torso_lean(person)
    shin = _shin_incline(person)
    diff = None if torso is None or shin is None else torso - shin
    visible_hip_knees = [
        (person[hip], person[knee])
        for hip, knee in (
            (KP.LEFT_HIP, KP.LEFT_KNEE),
            (KP.RIGHT_HIP, KP.RIGHT_KNEE),
        )
        if person[hip].visible and person[knee].visible
    ]
    hip_knee_offsets = [
        hip.y - knee.y for hip, knee in visible_hip_knees
    ]
    hip_knee_ratios = [
        (hip.y - knee.y) / max(math.hypot(hip.x - knee.x, hip.y - knee.y), 1e-6)
        for hip, knee in visible_hip_knees
    ]
    hip_knee_offset = (
        sum(hip_knee_offsets) / len(hip_knee_offsets)
        if hip_knee_offsets
        else None
    )
    hip_knee_ratio = (
        sum(hip_knee_ratios) / len(hip_knee_ratios)
        if hip_knee_ratios
        else None
    )

    sample.detected = True
    sample.knee_angle = _safe_round(knee)
    sample.femur_elevation = _safe_round(femur)
    sample.torso_incline = _safe_round(torso)
    sample.shin_incline = _safe_round(shin)
    sample.torso_shin_diff = _safe_round(diff)
    sample.hip_knee_vertical_offset = _safe_round(hip_knee_offset)
    sample.hip_knee_vertical_ratio = _safe_round(hip_knee_ratio)

    # 프로덕션 판정 경로 그대로: 대퇴 거상각 1차, 못 재면 무릎각 예비.
    if femur is not None and math.isfinite(femur):
        depth = check_depth_femur(femur, rep=1)
        sample.predicted_depth_code = depth.code
        sample.predicted_depth_issue = depth.code != "good_depth"
    elif knee is not None and math.isfinite(knee):
        depth = check_depth(knee, rep=1)
        sample.predicted_depth_code = depth.code
        sample.predicted_depth_issue = depth.code != "good_depth"

    torso_issue = check_torso(person, rep=1)
    if torso is not None and (shin is not None or torso > SQUAT_TORSO_LEAN_HARD_MAX):
        sample.predicted_torso_code = None if torso_issue is None else torso_issue.code
        sample.predicted_torso_issue = torso_issue is not None
    return sample


def confusion(truth: Iterable[bool], predicted: Iterable[bool]) -> dict[str, float | int]:
    pairs = list(zip(truth, predicted))
    tp = sum(t and p for t, p in pairs)
    tn = sum(not t and not p for t, p in pairs)
    fp = sum(not t and p for t, p in pairs)
    fn = sum(t and not p for t, p in pairs)
    total = len(pairs)

    def ratio(num: int, den: int) -> float:
        return round(num / den, 4) if den else 0.0

    sensitivity = ratio(tp, tp + fn)
    specificity = ratio(tn, tn + fp)
    return {
        "samples": total,
        "tp": tp,
        "tn": tn,
        "fp": fp,
        "fn": fn,
        "accuracy": ratio(tp + tn, total),
        "precision": ratio(tp, tp + fp),
        "recall": sensitivity,
        "specificity": specificity,
        "f1": ratio(2 * tp, 2 * tp + fp + fn),
        "balanced_accuracy": round((sensitivity + specificity) / 2, 4),
    }


def _candidate_thresholds(values: Iterable[float]) -> list[float]:
    unique = sorted(set(values))
    if not unique:
        return []
    candidates = [unique[0] - 0.001]
    candidates.extend((left + right) / 2 for left, right in zip(unique, unique[1:]))
    candidates.append(unique[-1] + 0.001)
    return candidates


def best_threshold(
    rows: list[Sample],
    value: Callable[[Sample], float | None],
    truth: Callable[[Sample], bool],
    current: float,
    hard_rule: Callable[[Sample], bool] | None = None,
) -> tuple[float, dict[str, float | int]]:
    usable = [(row, value(row)) for row in rows if value(row) is not None]
    if not usable:
        return current, confusion([], [])

    best: tuple[float, float, float, dict[str, float | int]] | None = None
    for threshold in _candidate_thresholds(v for _, v in usable if v is not None):
        truths = [truth(row) for row, _ in usable]
        predictions = [
            bool((hard_rule and hard_rule(row)) or (v is not None and v > threshold))
            for row, v in usable
        ]
        metrics = confusion(truths, predictions)
        # 클래스 불균형에 덜 흔들리는 balanced accuracy를 우선하고,
        # 동률이면 F1, 현재 임계값과의 거리 순으로 선택한다.
        rank = (
            float(metrics["balanced_accuracy"]),
            float(metrics["f1"]),
            -abs(threshold - current),
        )
        if best is None or rank > best[:3]:
            best = (*rank, metrics)
            best_threshold_value = threshold
    assert best is not None
    return round(best_threshold_value, 3), best[3]


def _task_rows(samples: list[Sample], task: str) -> list[Sample]:
    if task == "depth":
        return [s for s in samples if s.predicted_depth_issue is not None]
    return [s for s in samples if s.predicted_torso_issue is not None]


def current_metrics(samples: list[Sample], task: str) -> dict[str, float | int]:
    rows = _task_rows(samples, task)
    if task == "depth":
        return confusion(
            (s.truth_depth_issue for s in rows),
            (bool(s.predicted_depth_issue) for s in rows),
        )
    return confusion(
        (s.truth_torso_issue for s in rows),
        (bool(s.predicted_torso_issue) for s in rows),
    )


def conservative_depth_candidates(samples: list[Sample]) -> dict:
    """과적합을 줄이기 위해 사전에 고정한 5° 격자 후보를 모두 보고한다.

    지표는 현재 깊이 1차 지표인 대퇴 거상각. (무릎각 시절 격자는 80~100°였다)
    """
    rows = [row for row in samples if row.femur_elevation is not None]
    result = {}
    for threshold in (20.0, 25.0, 30.0, 35.0, 40.0):
        overall = confusion(
            (row.truth_depth_issue for row in rows),
            (bool(round(row.femur_elevation, 1) > threshold) for row in rows),
        )
        per_action = {}
        for action in DEFAULT_ACTIONS:
            action_rows = [row for row in rows if row.action == action]
            per_action[action] = confusion(
                (row.truth_depth_issue for row in action_rows),
                (bool(round(row.femur_elevation, 1) > threshold) for row in action_rows),
            )
        result[str(int(threshold))] = {
            "overall": overall,
            "per_action": per_action,
        }
    return result


def _threshold_report(
    rows: list[Sample],
    value: Callable[[Sample], float | None],
    truth: Callable[[Sample], bool],
    current: float,
    hard_rule: Callable[[Sample], bool] | None = None,
) -> dict:
    fitted, fitted_metrics = best_threshold(rows, value, truth, current, hard_rule)

    subjects = sorted({row.subject for row in rows}, key=int)
    folds = [subjects[index::5] for index in range(5)]
    cv_truth: list[bool] = []
    cv_predictions: list[bool] = []
    fold_thresholds: list[float] = []
    for test_subjects in folds:
        test_set = set(test_subjects)
        train_rows = [row for row in rows if row.subject not in test_set]
        test_rows = [row for row in rows if row.subject in test_set]
        threshold, _ = best_threshold(train_rows, value, truth, current, hard_rule)
        fold_thresholds.append(threshold)
        for row in test_rows:
            measured = value(row)
            if measured is None:
                continue
            cv_truth.append(truth(row))
            cv_predictions.append(
                bool((hard_rule and hard_rule(row)) or measured > threshold)
            )

    return {
        "current_threshold": current,
        "full_dataset_best_threshold": fitted,
        "full_dataset_best_metrics": fitted_metrics,
        "subject_5fold_cv": {
            "fold_thresholds": fold_thresholds,
            "mean_threshold": round(sum(fold_thresholds) / len(fold_thresholds), 3),
            "metrics": confusion(cv_truth, cv_predictions),
        },
    }


def threshold_analysis(samples: list[Sample], task: str) -> dict:
    rows = _task_rows(samples, task)
    if task == "depth":
        return _threshold_report(
            rows,
            value=lambda row: row.femur_elevation,
            truth=lambda row: row.truth_depth_issue,
            current=SQUAT_FEMUR_ELEVATION_WARN,
        )
    return _threshold_report(
        rows,
        value=lambda row: row.torso_shin_diff,
        truth=lambda row: row.truth_torso_issue,
        current=SQUAT_TORSO_SHIN_DIFF_WARN,
        hard_rule=lambda row: (
            row.torso_incline is not None
            and row.torso_incline > SQUAT_TORSO_LEAN_HARD_MAX
        ),
    )


def fms_aligned_diagnostics(samples: list[Sample]) -> dict:
    """현재 제품 규칙을 바꾸지 않고 FMS 정답과 직접 대응하는 지표를 비교한다."""
    depth_rows = [
        row for row in samples if row.hip_knee_vertical_ratio is not None
    ]
    torso_rows = [
        row for row in samples if row.torso_shin_diff is not None
    ]

    # 화면 y축은 아래가 양수다. 비율은 세로 오프셋을 대퇴 길이로 정규화한다.
    # COCO hip 관절점은 FMS의 육안상 hip crease보다 위에 잡히므로 0은 참고선일
    # 뿐이며, 실제 분리 임계값은 아래 교차검증으로 별도 측정한다.
    depth_truth = [row.truth_depth_issue for row in depth_rows]
    depth_prediction = [
        bool(row.hip_knee_vertical_ratio < 0)
        for row in depth_rows
        if row.hip_knee_vertical_ratio is not None
    ]

    # FMS의 "평행하지 않음"은 현재 signed diff가 아니라 차이의 절댓값에 대응한다.
    torso_truth = [row.truth_torso_issue for row in torso_rows]
    torso_prediction = [
        bool(
            row.torso_shin_diff is not None
            and abs(row.torso_shin_diff) > SQUAT_TORSO_SHIN_DIFF_WARN
        )
        for row in torso_rows
    ]

    return {
        "depth_by_hip_height": {
            "definition": "-(hip_y - knee_y) / femur_length > threshold",
            "metrics_at_zero": confusion(depth_truth, depth_prediction),
            "threshold_analysis": _threshold_report(
                depth_rows,
                # best_threshold는 값 > threshold를 양성으로 보므로 부호를 뒤집는다.
                value=lambda row: (
                    -row.hip_knee_vertical_ratio
                    if row.hip_knee_vertical_ratio is not None
                    else None
                ),
                truth=lambda row: row.truth_depth_issue,
                current=0.0,
            ),
        },
        "torso_by_absolute_parallel_difference": {
            "definition": "abs(torso_incline - shin_incline) > threshold",
            "metrics_at_current_warning_threshold": confusion(torso_truth, torso_prediction),
            "threshold_analysis": _threshold_report(
                torso_rows,
                value=lambda row: (
                    abs(row.torso_shin_diff)
                    if row.torso_shin_diff is not None
                    else None
                ),
                truth=lambda row: row.truth_torso_issue,
                current=SQUAT_TORSO_SHIN_DIFF_WARN,
            ),
        },
    }


def build_report(samples: list[Sample], actions: tuple[str, ...]) -> dict:
    detected = sum(sample.detected for sample in samples)
    both_available = [
        sample
        for sample in samples
        if sample.predicted_depth_issue is not None
        and sample.predicted_torso_issue is not None
    ]
    exact_match = sum(
        sample.truth_depth_issue == sample.predicted_depth_issue
        and sample.truth_torso_issue == sample.predicted_torso_issue
        for sample in both_available
    )

    per_action = {}
    for action in actions:
        action_rows = [sample for sample in samples if sample.action == action]
        per_action[action] = {
            "samples": len(action_rows),
            "detected": sum(sample.detected for sample in action_rows),
            "depth": current_metrics(action_rows, "depth"),
            "torso": current_metrics(action_rows, "torso"),
        }

    return {
        "dataset": {
            "name": "LLM-FMS",
            "doi": DATASET_DOI,
            "license": DATASET_LICENSE,
            "actions": list(actions),
            "samples": len(samples),
        },
        "mapping": {
            "depth_issue": "Hip height == Higher",
            "depth_ok": "Hip height in {Equal, Lower}",
            "torso_issue": "Trunk-calf angle == Not parallel",
            "torso_ok": "Trunk-calf angle == Parallel",
        },
        "coverage": {
            "pose_detected": detected,
            "pose_detection_rate": round(detected / len(samples), 4) if samples else 0.0,
            "both_feedbacks_available": len(both_available),
        },
        "current": {
            "depth": current_metrics(samples, "depth"),
            "torso": current_metrics(samples, "torso"),
            "exact_feedback_set": {
                "samples": len(both_available),
                "matches": exact_match,
                "accuracy": round(exact_match / len(both_available), 4)
                if both_available
                else 0.0,
            },
            "per_action": per_action,
        },
        "threshold_analysis": {
            "depth": threshold_analysis(samples, "depth"),
            "torso": threshold_analysis(samples, "torso"),
        },
        "conservative_depth_candidates": conservative_depth_candidates(samples),
        "fms_aligned_diagnostics": fms_aligned_diagnostics(samples),
        "limitations": [
            "LLM-FMS는 핵심 프레임 데이터이므로 반복 횟수 정확도를 검증하지 않는다.",
            "LLM-FMS 총점에는 손목 위치가 포함되지만 현재 모델은 손목을 평가하지 않는다.",
            "세부 라벨은 이진/범주형이므로 WARNING과 ERROR의 경계는 검증할 수 없다.",
            "FMS 오버헤드 딥 스쿼트와 앱의 일반 맨몸 스쿼트는 과제가 완전히 같지 않다.",
        ],
        "samples": [asdict(sample) for sample in samples],
    }


def write_csv(path: Path, samples: list[Sample]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = [asdict(sample) for sample in samples]
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]) if rows else [])
        if rows:
            writer.writeheader()
            writer.writerows(rows)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="LLM-FMS 딥 스쿼트 라벨과 현재 피드백 규칙의 일치도를 평가"
    )
    parser.add_argument(
        "--data-root",
        type=Path,
        default=Path("data/external/llm_fms"),
        help="FMS-Keyframes와 FMS-FineGrainedLabelInfo가 있는 경로",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/output/llm_fms_evaluation.json"),
    )
    parser.add_argument(
        "--csv-output",
        type=Path,
        default=Path("data/output/llm_fms_samples.csv"),
    )
    parser.add_argument("--model", default=None, help="YOLO pose 가중치 이름/경로")
    parser.add_argument(
        "--actions",
        nargs="+",
        choices=("m01", "m02"),
        default=list(DEFAULT_ACTIONS),
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    actions = tuple(args.actions)
    detector = PoseDetector(args.model) if args.model else PoseDetector()
    samples: list[Sample] = []
    for action in actions:
        label_dir = args.data_root / "FMS-FineGrainedLabelInfo" / action
        image_dir = args.data_root / "FMS-Keyframes" / action
        if not label_dir.is_dir() or not image_dir.is_dir():
            raise SystemExit(
                f"{action} 데이터가 없습니다. 라벨과 이미지 압축을 먼저 풀어 주세요: "
                f"{args.data_root}"
            )
        labels = sorted(label_dir.glob("*.json"))
        for index, label_path in enumerate(labels, start=1):
            samples.append(load_sample(label_path, image_dir, detector))
            if index % 25 == 0 or index == len(labels):
                print(f"{action}: {index}/{len(labels)}")

    report = build_report(samples, actions)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    write_csv(args.csv_output, samples)

    print(json.dumps({
        "coverage": report["coverage"],
        "current": {
            "depth": report["current"]["depth"],
            "torso": report["current"]["torso"],
            "exact_feedback_set": report["current"]["exact_feedback_set"],
        },
        "threshold_analysis": report["threshold_analysis"],
        "conservative_depth_candidates": report["conservative_depth_candidates"],
        "fms_aligned_diagnostics": report["fms_aligned_diagnostics"],
        "json": str(args.output),
        "csv": str(args.csv_output),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

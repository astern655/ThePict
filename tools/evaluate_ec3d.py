"""EC3D 스쿼트 시퀀스로 깊이 판정 기준 2종(무릎각 vs 엉덩이 높이)을 교차 검증한다.

LLM-FMS 검증(tools/evaluate_llm_fms.py)의 한계 보완이 목적이다. LLM-FMS의 깊이
정답은 문자 그대로 "Hip height"라서 엉덩이 높이 지표가 유리할 수밖에 없는
동어반복 편향이 있었다. EC3D의 라벨은 **지시된 오류 수행**("Not low enough"를
의도적으로 연기)이라 두 지표 어느 쪽과도 정의가 겹치지 않는 독립 심판이다.

데이터: EC3D (Zhao et al., ACCV 2022, "3D Pose Based Feedback for Physical
Exercises"). 모캡 3D 관절이므로 포즈 추정 노이즈 없이 **기준 기하 자체**를
비교한다. 시퀀스별 최저점을 측면(시상면) 투영 후 두 기준으로 판정한다.

라벨 숫자의 의미는 공개 코드에 문서화되어 있지 않아, 이 도구가 각 라벨의
기하 통계(최저 무릎각·엉덩이 높이·발 간격·상체 기울기)를 함께 출력해
1=정상, 2=발 넓음, 3=무릎 모임, 4=깊이 부족, 5=상체 숙임, 10=정상 변형
가설을 데이터로 검증한다.

사용:
    py -3 -m tools.evaluate_ec3d
    (data/external/ec3d/data_3D.pickle 필요 — README의 Google Drive에서 수동 확보)
"""
from __future__ import annotations

import argparse
import json
import math
import pickle
from collections import defaultdict
from pathlib import Path
from typing import Callable, Iterable

import numpy as np

# EC3D 25관절 스켈레톤 인덱스 (첫 프레임 좌표 기하로 추정, 뼈 길이 일관성으로 검증)
HIP_L, KNEE_L, ANKLE_L = 9, 10, 11
HIP_R, KNEE_R, ANKLE_R = 12, 13, 14
SHOULDER_L, SHOULDER_R = 2, 5
ROOT = 8

SQUAT_DEPTH_LABEL = 4          # "Not low enough" 가설 (출력의 기하 통계로 검증)
LABEL_NAMES = {
    1: "correct",
    2: "feet_too_wide",
    3: "knees_inward",
    4: "not_low_enough",
    5: "front_bent",
    10: "correct_variant",
}
# Plank 라벨(공개 코드의 map_label: [1, 7, 8]). 논문의 지시 오류는
# Arched back(허리 처짐)·Hunched back(등 솟음)이며, 숫자 대응은 출력의
# 방향 부호(엉덩이가 어깨-발목 선의 아래=처짐/위=솟음)로 검증한다.
PLANK_LABEL_NAMES = {1: "correct", 7: "arched_back", 8: "hunched_back"}


def load_sequences(path: Path, action: str = "SQUAT") -> dict[tuple, np.ndarray]:
    """(sub, lab, rep) -> (T, 3, 25) 프레임 시퀀스."""
    with path.open("rb") as fh:
        data = pickle.load(fh)
    labels = data["labels"]
    poses = data["poses"]
    seqs: dict[tuple, list] = defaultdict(list)
    for row, pose in zip(labels, poses):
        act, sub, lab, rep, frame = (str(v) for v in row)
        if act != action:
            continue
        seqs[(sub, int(lab), int(rep))].append((int(frame), pose))
    return {
        key: np.stack([p for _, p in sorted(frames)])
        for key, frames in seqs.items()
    }


def torso_shin_gap_at_bottom(arr: np.ndarray) -> float:
    """최저점(무릎각 최소 프레임)의 |상체 기울기 − 정강이 기울기| (도).

    ⚠️ EC3D 모캡은 프레임 방향이 **상체 기준으로 정규화**되어 있다(정상 딥스쿼트
    최저점의 절대 상체 기울기가 전 구간 0~1°로 나옴 — 물리적으로 불가능).
    따라서 절대각·부호는 쓸 수 없고, 회전 불변량인 **두 선분 사이 각의 크기**만
    유효하다. 스쿼트 최저점에서 큰 어긋남의 실제 방향은 전방 숙임이다
    (라벨 5가 지시된 front bend이고, 상체가 정강이보다 뒤로 눕는 자세는
    최저점에서 물리적으로 유지 불가). 프로덕션 지표(부호 있는 상체−정강이,
    ai/analysis/exercises/squat.py)의 크기 성분과 대응된다.
    """
    frames = []
    for pts3 in arr.transpose(0, 2, 1):
        side = project_side(pts3)
        knee = np.nanmean([
            angle_2d(side[HIP_L], side[KNEE_L], side[ANKLE_L]),
            angle_2d(side[HIP_R], side[KNEE_R], side[ANKLE_R]),
        ])
        frames.append((knee, side))
    knees = np.array([k for k, _ in frames])
    _, side = frames[int(np.nanargmin(knees))]
    mid_sh = (side[SHOULDER_L] + side[SHOULDER_R]) / 2
    mid_hip = (side[HIP_L] + side[HIP_R]) / 2
    knee_mid = (side[KNEE_L] + side[KNEE_R]) / 2
    ankle_mid = (side[ANKLE_L] + side[ANKLE_R]) / 2
    torso = math.degrees(math.atan2((mid_sh - mid_hip)[0], (mid_sh - mid_hip)[1]))
    shin = math.degrees(math.atan2((knee_mid - ankle_mid)[0], (knee_mid - ankle_mid)[1]))
    return abs(torso - shin)


def verify_skeleton(seqs: dict[tuple, np.ndarray]) -> dict:
    """관절 인덱스 가설 검증: 다리 뼈 길이가 프레임 간 일정한지(모캡이므로 ~0 분산)."""
    lengths = {"femur_l": [], "shin_l": [], "femur_r": [], "shin_r": []}
    for arr in seqs.values():
        pts = arr.transpose(0, 2, 1)  # (T, 25, 3)
        lengths["femur_l"].append(np.linalg.norm(pts[:, HIP_L] - pts[:, KNEE_L], axis=1))
        lengths["shin_l"].append(np.linalg.norm(pts[:, KNEE_L] - pts[:, ANKLE_L], axis=1))
        lengths["femur_r"].append(np.linalg.norm(pts[:, HIP_R] - pts[:, KNEE_R], axis=1))
        lengths["shin_r"].append(np.linalg.norm(pts[:, KNEE_R] - pts[:, ANKLE_R], axis=1))
    out = {}
    for name, chunks in lengths.items():
        vals = np.concatenate(chunks)
        out[name] = {
            "mean": round(float(vals.mean()), 4),
            "cv": round(float(vals.std() / vals.mean()), 4),  # 변동계수: 작아야 함
        }
    return out


def sagittal_frame(pts: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """프레임(25,3)에서 (전방, 수직) 시상면 축을 만든다. z가 수직축."""
    lateral = pts[HIP_R] - pts[HIP_L]
    lateral[2] = 0.0
    norm = np.linalg.norm(lateral)
    if norm < 1e-9:
        lateral = np.array([1.0, 0.0, 0.0])
    else:
        lateral = lateral / norm
    vertical = np.array([0.0, 0.0, 1.0])
    forward = np.cross(vertical, lateral)
    return forward, vertical


def project_side(pts: np.ndarray) -> np.ndarray:
    """(25,3) -> (25,2) 시상면 투영. [:,0]=전방, [:,1]=수직(위가 양수)."""
    forward, vertical = sagittal_frame(pts)
    return np.stack([pts @ forward, pts @ vertical], axis=1)


def angle_2d(a: np.ndarray, b: np.ndarray, c: np.ndarray) -> float:
    """b를 꼭짓점으로 하는 2D 관절각(도). 프로덕션 geometry.joint_angle과 동일 정의."""
    v1, v2 = a - b, c - b
    n1, n2 = np.linalg.norm(v1), np.linalg.norm(v2)
    if n1 < 1e-9 or n2 < 1e-9:
        return float("nan")
    cos = float(np.clip(np.dot(v1, v2) / (n1 * n2), -1.0, 1.0))
    return math.degrees(math.acos(cos))


def measure_sequence(arr: np.ndarray) -> dict:
    """시퀀스 하나의 최저점 측정값.

    무릎각·엉덩이높이 각각 **자기 신호의 최저점**에서 판정한다. 프로덕션이
    자기 신호(무릎각)의 최저 프레임을 스냅샷으로 쓰는 방식과 대응된다.
    """
    knees, hips, spans, torsos, widths = [], [], [], [], []
    for pts3 in arr.transpose(0, 2, 1):  # (25, 3) per frame
        side = project_side(pts3)
        knee = np.nanmean([
            angle_2d(side[HIP_L], side[KNEE_L], side[ANKLE_L]),
            angle_2d(side[HIP_R], side[KNEE_R], side[ANKLE_R]),
        ])
        # 엉덩이 높이: (hip_v - knee_v) / 대퇴 투영 길이 = 대퇴가 수평 위로 든 sin.
        # 프로덕션 hip_knee_vertical_ratio(화면 y 아래 양수)의 부호 반전판과 동일.
        ratios = []
        for hip, kn in ((HIP_L, KNEE_L), (HIP_R, KNEE_R)):
            femur = np.linalg.norm(side[hip] - side[kn])
            if femur > 1e-9:
                ratios.append((side[hip][1] - side[kn][1]) / femur)
        hip_ratio = float(np.mean(ratios)) if ratios else float("nan")
        # hip_in_span: 엉덩이가 무릎~발목 수직 구간의 어디에 있는가.
        # 대퇴 투영 길이가 아니라 정강이의 수직 성분으로 정규화한다.
        # (LLM-FMS 특징 탐색에서 대퇴 길이 정규화보다 CV 성능이 높았다)
        spans_here = []
        for hip, kn, ank in ((HIP_L, KNEE_L, ANKLE_L), (HIP_R, KNEE_R, ANKLE_R)):
            denom = side[kn][1] - side[ank][1]   # 무릎이 발목보다 위 → 양수
            if abs(denom) > 1e-9:
                spans_here.append((side[hip][1] - side[kn][1]) / denom)
        span = float(np.mean(spans_here)) if spans_here else float("nan")
        # 라벨 매핑 검증용 보조 측정
        mid_sh = (side[SHOULDER_L] + side[SHOULDER_R]) / 2
        mid_hip = (side[HIP_L] + side[HIP_R]) / 2
        t = mid_sh - mid_hip
        torso = math.degrees(math.atan2(abs(t[0]), t[1])) if np.linalg.norm(t) > 1e-9 else float("nan")
        knees.append(knee)
        hips.append(hip_ratio)
        spans.append(span)
        torsos.append(torso)
        widths.append(float(np.linalg.norm(pts3[ANKLE_L] - pts3[ANKLE_R])))
    knees, hips, spans = np.array(knees), np.array(hips), np.array(spans)
    return {
        "min_knee_angle": round(float(np.nanmin(knees)), 2),
        # 각 신호의 최저점: 시퀀스에서 엉덩이가 가장 낮았던 순간의 비율
        "min_hip_ratio": round(float(np.nanmin(hips)), 4),
        "min_hip_in_span": round(float(np.nanmin(spans)), 4),
        "bottom_torso_incline": round(float(torsos[int(np.nanargmin(knees))]), 2),
        "max_ankle_width": round(max(widths), 4),
        "frames": len(knees),
    }


def measure_plank_sequence(arr: np.ndarray) -> dict:
    """플랭크 시퀀스의 몸통 일직선 측정값.

    푸시업 `check_body_line`과 같은 정의: 이탈각 = 180 − (어깨-엉덩이-발목각).
    방향은 부호로 남긴다(음수 = 엉덩이가 어깨-발목 선 **아래** = 허리 처짐).
    플랭크는 정적 유지 동작이라 프레임 중앙값을 시퀀스 대표값으로 쓴다.
    """
    devs, signed = [], []
    for pts3 in arr.transpose(0, 2, 1):
        side = project_side(pts3)
        sh = (side[SHOULDER_L] + side[SHOULDER_R]) / 2
        hip = (side[HIP_L] + side[HIP_R]) / 2
        ank = (side[ANKLE_L] + side[ANKLE_R]) / 2
        dev = 180.0 - angle_2d(sh, hip, ank)
        if not math.isfinite(dev):
            continue
        # 방향: 어깨-발목 선의 같은 전방 위치에서 엉덩이의 수직 편차(위=양수)
        vx = ank[0] - sh[0]
        if abs(vx) < 1e-9:
            continue
        t = (hip[0] - sh[0]) / vx
        line_v = sh[1] + t * (ank[1] - sh[1])
        above = hip[1] > line_v          # 투영의 [:,1]은 위가 양수
        devs.append(dev)
        signed.append(dev if above else -dev)
    return {
        "median_body_dev": round(float(np.median(devs)), 2) if devs else float("nan"),
        "median_signed_dev": round(float(np.median(signed)), 2) if signed else float("nan"),
        "max_body_dev": round(float(np.max(devs)), 2) if devs else float("nan"),
        "frames": len(devs),
    }


def confusion(truth: Iterable[bool], pred: Iterable[bool]) -> dict:
    pairs = list(zip(truth, pred))
    tp = sum(t and p for t, p in pairs)
    tn = sum(not t and not p for t, p in pairs)
    fp = sum(not t and p for t, p in pairs)
    fn = sum(t and not p for t, p in pairs)
    n = len(pairs)

    def ratio(num: int, den: int) -> float:
        return round(num / den, 4) if den else 0.0

    rec, spec = ratio(tp, tp + fn), ratio(tn, tn + fp)
    return {
        "samples": n, "tp": tp, "tn": tn, "fp": fp, "fn": fn,
        "accuracy": ratio(tp + tn, n), "precision": ratio(tp, tp + fp),
        "recall": rec, "specificity": spec,
        "f1": ratio(2 * tp, 2 * tp + fp + fn),
        "balanced_accuracy": round((rec + spec) / 2, 4),
    }


def auc(rows: list[dict], key: str, flip: bool = False) -> float:
    """Mann-Whitney ROC-AUC. flip=True면 값이 클수록 양성."""
    pos = [r[key] for r in rows if r["truth"]]
    neg = [r[key] for r in rows if not r["truth"]]
    if not pos or not neg:
        return float("nan")
    wins = sum(
        1.0 if (p > n_) == (not flip) else (0.5 if p == n_ else 0.0)
        for p in pos for n_ in neg
    )
    # key 값이 "클수록 얕음"이 되도록 호출부에서 부호를 맞추므로 flip 기본 False
    return round(wins / (len(pos) * len(neg)), 4)


def best_recall_at_spec(rows: list[dict], key: str, min_spec: float) -> dict:
    """특이도 제약 하 재현율 최대 임계값(값 > t = 깊이부족 판정)."""
    vals = sorted({r[key] for r in rows})
    cands = [vals[0] - 1e-6] + [(a + b) / 2 for a, b in zip(vals, vals[1:])] + [vals[-1] + 1e-6]
    truth = [r["truth"] for r in rows]
    best = None
    for t in cands:
        m = confusion(truth, [r[key] > t for r in rows])
        if m["specificity"] < min_spec:
            continue
        if best is None or (m["recall"], m["balanced_accuracy"]) > (best[1]["recall"], best[1]["balanced_accuracy"]):
            best = (t, m)
    if best is None:
        return {"threshold": None, "metrics": None}
    return {"threshold": round(best[0], 4), "metrics": best[1]}


def loso_cv(rows: list[dict], key: str, min_spec: float) -> dict:
    """피험자 단위 leave-one-subject-out 교차검증."""
    subjects = sorted({r["subject"] for r in rows})
    truth, pred = [], []
    fold_thresholds = []
    for held in subjects:
        train = [r for r in rows if r["subject"] != held]
        test = [r for r in rows if r["subject"] == held]
        picked = best_recall_at_spec(train, key, min_spec)
        t = picked["threshold"]
        if t is None:
            continue
        fold_thresholds.append(round(t, 4))
        truth.extend(r["truth"] for r in test)
        pred.extend(r[key] > t for r in test)
    return {"fold_thresholds": fold_thresholds, "metrics": confusion(truth, pred)}


def main() -> int:
    parser = argparse.ArgumentParser(description="EC3D 스쿼트 깊이 기준 교차 검증")
    parser.add_argument("--data", type=Path, default=Path("data/external/ec3d/data_3D.pickle"))
    parser.add_argument("--output", type=Path, default=Path("data/output/ec3d_evaluation.json"))
    parser.add_argument("--min-spec", type=float, default=0.90)
    args = parser.parse_args()

    if not args.data.is_file():
        raise SystemExit(f"데이터가 없습니다: {args.data}")

    seqs = load_sequences(args.data)
    skeleton_check = verify_skeleton(seqs)

    rows = []
    for (sub, lab, rep), arr in sorted(seqs.items()):
        m = measure_sequence(arr)
        rows.append({
            "subject": sub, "label": lab, "label_name": LABEL_NAMES.get(lab, f"unknown_{lab}"),
            "rep": rep, "truth": lab == SQUAT_DEPTH_LABEL,
            # 판정값: 클수록 얕음. 무릎각은 그대로, 엉덩이는 최저 비율 그대로
            # (비율이 높게 유지 = 끝까지 엉덩이가 안 내려감).
            "knee": m["min_knee_angle"], "hip": m["min_hip_ratio"],
            "span": m["min_hip_in_span"],
            "torso_gap": round(torso_shin_gap_at_bottom(arr), 2),
            **m,
        })

    # 라벨 매핑 검증: 라벨별 기하 요약
    label_stats = {}
    for lab in sorted({r["label"] for r in rows}):
        grp = [r for r in rows if r["label"] == lab]
        label_stats[f"{lab}:{LABEL_NAMES.get(lab, '?')}"] = {
            "sequences": len(grp),
            "min_knee_angle_median": round(float(np.median([g["min_knee_angle"] for g in grp])), 1),
            "min_hip_ratio_median": round(float(np.median([g["min_hip_ratio"] for g in grp])), 3),
            "bottom_torso_median": round(float(np.median([g["bottom_torso_incline"] for g in grp])), 1),
            "ankle_width_median": round(float(np.median([g["max_ankle_width"] for g in grp])), 3),
        }

    # --- 스쿼트 상체(전방 숙임) 규칙 검증: front_bent(5) vs 정상(1,10) --------
    # 프로덕션 SQUAT_TORSO_SHIN_DIFF_WARN(30°)의 첫 결함-양성 검증. 정규화 탓에
    # |차|만 유효하다(torso_shin_gap_at_bottom의 주석). 모캡→YOLO/COCO 전이
    # 주의는 깊이 지표와 동일 — 임계값 숫자 자체를 여기서 가져오지 말 것.
    torso_ok = [r for r in rows if r["label"] in (1, 10)]
    torso_bad = [r for r in rows if r["label"] == 5]
    wins = sum(
        1.0 if b["torso_gap"] > o["torso_gap"] else 0.5 if b["torso_gap"] == o["torso_gap"] else 0.0
        for b in torso_bad for o in torso_ok
    )
    torso_thresholds = {}
    for th in (15.0, 20.0, 25.0, 30.0):
        torso_thresholds[f"|gap|>{th:.0f}"] = {
            "front_bent_recall": f"{sum(1 for r in torso_bad if r['torso_gap'] > th)}/{len(torso_bad)}",
            "correct_fp": f"{sum(1 for r in torso_ok if r['torso_gap'] > th)}/{len(torso_ok)}",
            "other_defect_over": {
                LABEL_NAMES[l]: sum(1 for r in rows if r["label"] == l and r["torso_gap"] > th)
                for l in (2, 3, 4)
            },
        }
    squat_torso = {
        "purpose": "상체-정강이 상대각 지표의 결함 양성(지시된 전방 숙임) 판별력 검증. "
                   "LLM-FMS r01은 '상체가 덜 기움' 방향이 지배적이라 전방 숙임 검증이 "
                   "불가능했다(docs/SQUAT_TUNING.md §상체).",
        "orientation_note": "모캡이 상체 방향을 정규화해 절대각·부호 사용 불가 — |차|만 유효",
        "auc_abs_gap": round(wins / (len(torso_bad) * len(torso_ok)), 3) if torso_bad and torso_ok else None,
        "correct_gap_median_max": [
            round(float(np.median([r["torso_gap"] for r in torso_ok])), 1),
            round(max(r["torso_gap"] for r in torso_ok), 1),
        ],
        "front_bent_gap_median_range": [
            round(float(np.median([r["torso_gap"] for r in torso_bad])), 1),
            round(min(r["torso_gap"] for r in torso_bad), 1),
            round(max(r["torso_gap"] for r in torso_bad), 1),
        ],
        "thresholds": torso_thresholds,
        "per_subject_median": {
            sub: {
                "correct": round(float(np.median(
                    [r["torso_gap"] for r in torso_ok if r["subject"] == sub])), 1),
                "front_bent": round(float(np.median(
                    [r["torso_gap"] for r in torso_bad if r["subject"] == sub])), 1),
            }
            for sub in sorted({r["subject"] for r in torso_bad})
        },
    }

    # --- Plank: 푸시업 몸통 일직선 규칙의 독립 검증 -------------------------
    plank_rows = []
    for (sub, lab, rep), arr in sorted(load_sequences(args.data, "Plank").items()):
        m = measure_plank_sequence(arr)
        plank_rows.append({
            "subject": sub, "label": lab,
            "label_name": PLANK_LABEL_NAMES.get(lab, f"unknown_{lab}"),
            "rep": rep, "truth": lab != 1,
            # 판정값: 이탈각 중앙값(클수록 결함) — 푸시업 WARN 15°/SEVERE 25°와 동일 지표
            "dev": m["median_body_dev"], **m,
        })
    plank_label_stats = {}
    for lab in sorted({r["label"] for r in plank_rows}):
        grp = [r for r in plank_rows if r["label"] == lab]
        plank_label_stats[f"{lab}:{PLANK_LABEL_NAMES.get(lab, '?')}"] = {
            "sequences": len(grp),
            "median_dev": round(float(np.median([g["median_body_dev"] for g in grp])), 1),
            "median_signed_dev": round(float(np.median([g["median_signed_dev"] for g in grp])), 1),
        }
    plank_current = confusion(
        (r["truth"] for r in plank_rows),
        (r["dev"] > 15.0 for r in plank_rows),  # 현재 운영 WARN 경계
    )

    report = {
        "dataset": {
            "name": "EC3D (3D Pose Based Feedback for Physical Exercises, ACCV 2022)",
            "sequences": len(rows),
            "subjects": sorted({r["subject"] for r in rows}),
            "depth_label_hypothesis": f"{SQUAT_DEPTH_LABEL} == not_low_enough",
        },
        "plank_body_line": {
            "purpose": "푸시업 몸통 일직선 규칙(어깨-엉덩이-발목 이탈각)의 독립 검증. "
                       "로컬 푸시업 라벨에는 몸통 결함 양성이 0이라 여기서만 재현율을 잴 수 있다.",
            "sequences": len(plank_rows),
            "label_geometry": plank_label_stats,
            "auc": auc(plank_rows, "dev"),
            "metrics_at_current_warn_15deg": plank_current,
            "recall_at_spec": best_recall_at_spec(plank_rows, "dev", args.min_spec),
            "leave_one_subject_out": loso_cv(plank_rows, "dev", args.min_spec),
        },
        "squat_torso": squat_torso,
        "skeleton_bone_length_check": skeleton_check,
        "label_geometry": label_stats,
        "auc": {
            "knee_angle": auc(rows, "knee"),
            "hip_ratio": auc(rows, "hip"),
            "hip_in_span": auc(rows, "span"),
        },
        "recall_at_spec": {
            "constraint": f"specificity >= {args.min_spec}",
            "knee_angle": best_recall_at_spec(rows, "knee", args.min_spec),
            "hip_ratio": best_recall_at_spec(rows, "hip", args.min_spec),
            "hip_in_span": best_recall_at_spec(rows, "span", args.min_spec),
        },
        "leave_one_subject_out": {
            "knee_angle": loso_cv(rows, "knee", args.min_spec),
            "hip_ratio": loso_cv(rows, "hip", args.min_spec),
            "hip_in_span": loso_cv(rows, "span", args.min_spec),
        },
        "sequences": rows,
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    summary = {k: v for k, v in report.items() if k != "sequences"}
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"\n전체 리포트: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

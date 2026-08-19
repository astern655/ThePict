"""MM-Fit 데이터셋으로 푸시업 rep 카운트 외부 검증.

데이터: MM-Fit (mmfit.github.io, IMWUT'20). 21개 워크아웃(피험자별 세션)의
2D 포즈(OpenPose 18관절, 정면 RGB-D 카메라 30Hz)와 전문가 라벨(세트별 프레임
구간 + 반복 수). 푸시업 65세트 653 rep. 포즈·라벨만 로컬 보관
(`data/external/mmfit/`, 코드 MIT / RGB는 Zenodo CC BY 4.0 — 미다운로드).

⚠️ 검증 범위: 이 평가는 **rep 카운트 로직(평활 → 적응 임계 → 히스테리시스 →
깊이 가드)의 신호 소스 독립 검증**이다. 관절 좌표가 우리 제품 경로(YOLO,
측면 촬영)가 아니라 MM-Fit의 자체 포즈(정면 시점)에서 오므로, YOLO 검출
품질·측면 판정은 여기서 검증되지 않는다. (EC3D로 규칙 기하를 검증한 것과
같은 성격이다.)

정면 시점 주의: 푸시업을 정면(머리 쪽)에서 내려다보는 카메라라 팔꿈치각의
2D 투영 진폭이 측면보다 작을 수 있다 — 적응 임계가 영상별로 폭을 잡으므로
동작하지만, 폭이 MIN_SPAN(25°) 미만이면 고정 임계로 떨어져 0회가 될 수 있다.
그 경우도 실패로 집계한다(감추지 않는다).

실행: py -3 -m tools.evaluate_mmfit
출력: data/output/mmfit_evaluation.json
"""
from __future__ import annotations

import csv
import json
import math
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools" / "experiments"))
from rep_lab import count_reps  # noqa: E402

from ai.config import (  # noqa: E402
    PUSHUP_ADAPTIVE_DOWN_RATIO,
    PUSHUP_ADAPTIVE_MIN_SPAN,
    PUSHUP_ADAPTIVE_UP_RATIO,
    PUSHUP_ANGLE_SMOOTH_WINDOW,
    PUSHUP_ELBOW_DOWN_ANGLE,
    PUSHUP_ELBOW_UP_ANGLE,
    PUSHUP_REP_PROMINENCE,
)

ROOT = Path("data/external/mmfit/mm-fit")
OUT = Path("data/output/mmfit_evaluation.json")
FPS = 30.0
# 라벨 구간 앞뒤 여유(초). 엔진은 세트 앞뒤의 준비/정리 프레임도 함께 보므로
# 완전히 잘라낸 구간만 주면 오히려 비현실적으로 쉬워진다. 2초면 자세 진입이
# 들어오고 인접 세트(최소 수백 프레임 간격)와 겹치지 않는다.
MARGIN_SEC = 2.0

# OpenPose BODY-18 관절 순서(열 0은 프레임 번호라 +1 오프셋).
R_SHOULDER, R_ELBOW, R_WRIST = 2, 3, 4
L_SHOULDER, L_ELBOW, L_WRIST = 5, 6, 7

REP_PARAMS = dict(
    down_ratio=PUSHUP_ADAPTIVE_DOWN_RATIO, up_ratio=PUSHUP_ADAPTIVE_UP_RATIO,
    min_span=PUSHUP_ADAPTIVE_MIN_SPAN, window=PUSHUP_ANGLE_SMOOTH_WINDOW,
    fixed_down=PUSHUP_ELBOW_DOWN_ANGLE, fixed_up=PUSHUP_ELBOW_UP_ANGLE,
    prominence=PUSHUP_REP_PROMINENCE,
)


def _angle_at(a, b, c) -> float | None:
    """꼭짓점 b의 각도(도). 겹친 좌표면 None — 엔진 landmarks.angle_at과 동일 규칙."""
    v1 = (a[0] - b[0], a[1] - b[1])
    v2 = (c[0] - b[0], c[1] - b[1])
    n1 = math.hypot(*v1)
    n2 = math.hypot(*v2)
    if n1 < 1e-6 or n2 < 1e-6:
        return None
    cos = max(-1.0, min(1.0, (v1[0] * v2[0] + v1[1] * v2[1]) / (n1 * n2)))
    return math.degrees(math.acos(cos))


def _joint(pose, frame_idx: int, joint: int):
    """(x, y). MM-Fit은 미검출 관절 신뢰도가 없어 (0,0) 좌표를 미검출로 간주한다."""
    x = pose[0, frame_idx, joint + 1]
    y = pose[1, frame_idx, joint + 1]
    if x == 0 and y == 0:
        return None
    return (x, y)


def elbow_series(pose, start: int, end: int) -> list[tuple[int, float]]:
    """[프레임, 팔꿈치각(양팔 평균)] — 엔진 _elbow_angle과 같은 좌우 평균 규칙."""
    frames = pose[0, :, 0]
    idx = np.where((frames >= start) & (frames <= end))[0]
    out = []
    for i in idx:
        angles = []
        for sh, el, wr in ((R_SHOULDER, R_ELBOW, R_WRIST),
                           (L_SHOULDER, L_ELBOW, L_WRIST)):
            pts = [_joint(pose, i, j) for j in (sh, el, wr)]
            if all(p is not None for p in pts):
                ang = _angle_at(pts[0], pts[1], pts[2])
                if ang is not None:
                    angles.append(ang)
        if angles:
            out.append((int(frames[i]), sum(angles) / len(angles)))
    return out


def main() -> int:
    margin = int(MARGIN_SEC * FPS)
    rows = []
    for wdir in sorted(ROOT.iterdir()):
        lab = wdir / f"{wdir.name}_labels.csv"
        pose_path = wdir / f"{wdir.name}_pose_2d.npy"
        if not (lab.exists() and pose_path.exists()):
            continue
        with lab.open() as fh:
            sets = [(int(r[0]), int(r[1]), int(r[2]), r[3])
                    for r in csv.reader(fh)]
        pushups = [(s, e, n) for s, e, n, name in sets if name == "pushups"]
        if not pushups:
            continue
        pose = np.load(pose_path)
        for set_i, (s, e, truth) in enumerate(pushups, start=1):
            series = elbow_series(pose, s - margin, e + margin)
            n, _reps = count_reps(series, FPS, **REP_PARAMS)
            rows.append({
                "workout": wdir.name, "set": set_i,
                "engine": n, "truth": truth, "err": n - truth,
                "measured_frames": len(series),
            })
            print(f"{wdir.name} set{set_i}: 엔진 {n} / 정답 {truth}"
                  + ("" if n == truth else f"  ← 오차 {n - truth:+d}"), flush=True)

    exact = sum(r["engine"] == r["truth"] for r in rows)
    abs_err = sum(abs(r["err"]) for r in rows)
    total = sum(r["truth"] for r in rows)
    summary = {
        "sets": len(rows), "exact_sets": exact,
        "exact_rate": round(exact / len(rows), 4),
        "total_truth_reps": total, "total_abs_err": abs_err,
        "count_accuracy": round(max(0.0, 1 - abs_err / total), 4),
        "worst": max((abs(r["err"]) for r in rows), default=0),
    }
    print("\n== 종합 ==")
    print(f"세트 {summary['sets']} / 정확 {exact} ({summary['exact_rate']:.1%})")
    print(f"총 {total} rep, 절대 오차 합 {abs_err}, "
          f"카운트 정확도 {summary['count_accuracy']:.1%}, 최악 {summary['worst']}")

    OUT.write_text(json.dumps({
        "dataset": "MM-Fit pushups (2D pose, frontal RGB-D) — 카운트 로직 검증",
        "params": {k: v for k, v in REP_PARAMS.items()},
        "margin_sec": MARGIN_SEC,
        "summary": summary,
        "per_set": rows,
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n저장: {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

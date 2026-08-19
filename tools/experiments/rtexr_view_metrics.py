"""RTExR 시점 라벨 60편의 게이트 지표 실측 + 측면 클립의 rep 기록 수집.

목적 두 가지(YOLO 패스를 한 번에):
1. 게이트 개선 — 미검출 3건이 세 지표에서 임계와 얼마나 떨어져 있는지,
   임계를 조이면 측면 33편의 여유가 얼마나 남는지.
2. 몸통 델타 양성 검증 가능성 — 측면 클립 중 기준선이 잡히는 클립과
   rep별 델타·top 프레임 번호(육안 라벨용) 목록.

실행: py -3 tools/experiments/rtexr_view_metrics.py
출력: data/output/rtexr_view_metrics.json
"""
import json
import statistics
import sys
from pathlib import Path

import cv2

sys.path.insert(0, str(Path.cwd()))
from ai.analysis.exercises import create_analyzer  # noqa: E402
from ai.config import pose_model_for  # noqa: E402
from ai.pose.detector import PoseDetector  # noqa: E402
from tools.experiments.view_probe import frame_metrics  # noqa: E402

ROOT = Path("data/external/rtexr")
OUT = Path("data/output/rtexr_view_metrics.json")
LABELS = json.loads((ROOT / "view_labels.json").read_text(encoding="utf-8"))


def main() -> int:
    detector = PoseDetector(pose_model_for("pushup"))
    rows = []
    if OUT.exists():
        rows = json.loads(OUT.read_text(encoding="utf-8"))
    done = {r["video"] for r in rows}
    for vid, view in LABELS.items():
        if vid.startswith("_") or vid in done:
            continue
        path = ROOT / f"{vid}.mp4"
        if not path.exists():
            continue
        cap = cv2.VideoCapture(str(path))
        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        analyzer = create_analyzer("pushup", fps=fps)
        samples: dict[str, list[float]] = {}
        idx = 0
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            person = detector.detect(frame)
            analyzer.update(person, idx)
            if person is not None:
                for k, v in frame_metrics(person).items():
                    samples.setdefault(k, []).append(v)
            idx += 1
        cap.release()
        report = analyzer.finalize()
        row = {"video": vid, "view": view,
               "baseline": report.body_line_baseline,
               "rep_count": report.rep_count,
               "video_codes": [i.code for i in report.video_issues],
               "reps": [{"rep": r.rep_index, "start": r.start_frame,
                         "bottom": r.bottom_frame,
                         "top_dev": r.top_body_line_dev,
                         "delta": r.top_body_line_delta}
                        for r in report.reps]}
        for k, vals in samples.items():
            if not k.endswith("_n") and len(vals) >= 10:
                row[k] = round(statistics.median(vals), 3)
        rows.append(row)
        OUT.write_text(json.dumps(rows, ensure_ascii=False, indent=1),
                       encoding="utf-8")
        shown = {k: row.get(k) for k in ("cur", "hip_gap", "horiz") if k in row}
        print(f"{vid} [{view}] {shown} 기준선={row['baseline']}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

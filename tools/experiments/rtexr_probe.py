"""RTExR(Real-Time Exercise Recognition Dataset) 푸시업으로 신선 검증.

데이터: huggingface.co/datasets/RickyRiccio/Real_Time_Exercise_Recognition_Dataset
푸시업 부분만 원격 선별 추출(data/external/rtexr/, 140편 105MB) —
InfiniteRep 합성 100(다양한 카메라 각도, CC BY 4.0) + Kaggle 실영상 25 +
유사 수집 12 + 저자 테스트 3.

한 번의 YOLO 패스로 두 가지를 뽑는다.
1. 엔진 리포트(rep 카운트·게이트·몸통) — 강화 게이트의 실전 분포 확인
2. GT 라벨용 보조 신호 — 손목 대비 어깨 높이 ÷ 몸통(팔꿈치각과 무관한
   신호, §7-0의 정답 프로토콜). 사람이 이 스파크라인으로 rep을 센다.

실행: py -3 tools/experiments/rtexr_probe.py
출력: data/output/rtexr_probe.json (영상별, 재개 가능)
"""
import json
import statistics
import sys
from pathlib import Path

import cv2

sys.path.insert(0, str(Path.cwd()))
from ai.analysis.exercises import create_analyzer  # noqa: E402
from ai.analysis.landmarks import torso_length, visible_all  # noqa: E402
from ai.config import pose_model_for  # noqa: E402
from ai.pose.detector import PoseDetector  # noqa: E402
from ai.pose.keypoints import KP  # noqa: E402

ROOT = Path("data/external/rtexr")
OUT = Path("data/output/rtexr_probe.json")


def gt_signal(person) -> float | None:
    """손목 대비 어깨 높이 ÷ 몸통 길이. 팔을 펴면 크고 바닥에 붙으면 작다."""
    torso = torso_length(person)
    if not torso:
        return None
    vals = []
    for sh, wr in ((KP.LEFT_SHOULDER, KP.LEFT_WRIST),
                   (KP.RIGHT_SHOULDER, KP.RIGHT_WRIST)):
        if visible_all(person, (sh, wr)):
            vals.append((person[wr].y - person[sh].y) / torso)
    if not vals:
        return None
    return sum(vals) / len(vals)


def main() -> int:
    detector = PoseDetector(pose_model_for("pushup"))
    rows = []
    if OUT.exists():
        rows = json.loads(OUT.read_text(encoding="utf-8"))
    done = {r["video"] for r in rows}
    for path in sorted(ROOT.glob("*.mp4")):
        if path.name in done:
            continue
        cap = cv2.VideoCapture(str(path))
        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        analyzer = create_analyzer("pushup", fps=fps)
        signal = []
        idx = 0
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            person = detector.detect(frame)
            analyzer.update(person, idx)
            if person is not None:
                s = gt_signal(person)
                if s is not None:
                    signal.append((idx, round(s, 3)))
            idx += 1
        cap.release()
        report = analyzer.finalize()
        # GT용 신호를 초당 ~8표본으로 줄여 저장(사람이 셀 해상도로 충분)
        step = max(1, round(fps / 8))
        rows.append({
            "video": path.name, "frames": idx, "fps": round(fps, 2),
            "engine": report.rep_count, "partial": report.partial_rep_count,
            "video_codes": [i.code for i in report.video_issues],
            "gt_signal": [v for f, v in signal if f % step == 0],
            "gt_signal_fps": round(fps / step, 1),
        })
        OUT.write_text(json.dumps(rows, ensure_ascii=False),
                       encoding="utf-8")
        print(f"{path.name}: rep {report.rep_count} 코드 "
              f"{[i.code for i in report.video_issues]}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

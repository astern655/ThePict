"""푸시업 몸통 캘리브레이션 연구용 프레임 캐시 (영상별 증분 저장).

프레임마다 [idx, 팔꿈치각(원시), 몸통 이탈각, 방향(1=처짐/0=솟음/null=불명)]을
남긴다. 목적: 기준선 캘리브레이션 판정(2026-08-14 도입)이 로컬 정상 rep에서
오탐 17건을 낸 원인 진단과, 기준선 정의·δ 임계의 오프라인 재도출.
(YOLO 재실행 없이 tools/experiments/body_lab.py에서 전략을 비교한다)

사용: py -3 tools/experiments/cache_pushup_body.py <출력폴더> [local|pushai|both]
"""
import json
import sys
from pathlib import Path

import cv2

sys.path.insert(0, str(Path.cwd()))
from ai.analysis.exercises.pushup import _body_line_deviation, _elbow_angle  # noqa: E402
from ai.config import (  # noqa: E402
    VIDEO_FPS_FALLBACK, VIDEO_FPS_MAX, VIDEO_FPS_MIN, pose_model_for,
)
from ai.pose.detector import PoseDetector  # noqa: E402

OUT = Path(sys.argv[1])
WHICH = sys.argv[2] if len(sys.argv) > 2 else "both"


def series(video: Path, detector: PoseDetector):
    cap = cv2.VideoCapture(str(video))
    fps = cap.get(cv2.CAP_PROP_FPS) or 0.0
    if not (VIDEO_FPS_MIN <= fps <= VIDEO_FPS_MAX):
        fps = VIDEO_FPS_FALLBACK
    detector.reset()
    out = []
    idx = 0
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        try:
            person = detector.detect(frame)
        except Exception:
            person = None
        if person is not None:
            angle = _elbow_angle(person)
            measured = _body_line_deviation(person)
            if angle is not None or measured is not None:
                dev, below = (None, None) if measured is None else measured
                out.append([
                    idx,
                    None if angle is None else round(angle, 2),
                    None if dev is None else round(dev, 2),
                    None if below is None else int(below),
                ])
        idx += 1
        if idx % 500 == 0:
            print(f"    {video.stem[:12]} {idx}프레임", flush=True)
    cap.release()
    return fps, idx, out


def dump(dest: Path, video: Path, detector: PoseDetector, meta: dict) -> None:
    if dest.exists():
        print(f"skip {dest.stem}", flush=True)
        return
    fps, frames, rows = series(video, detector)
    dest.write_text(json.dumps(
        {"fps": fps, "frames": frames, "rows": rows, **meta}), encoding="utf-8")
    print(f"{dest.stem}: 측정 {len(rows)}/{frames}프레임", flush=True)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    detector = PoseDetector(pose_model_for("pushup"))

    if WHICH in ("local", "both"):
        labels = json.loads(
            Path("data/pushup_labels.json").read_text(encoding="utf-8"))
        for entry in labels:
            vid = entry["id"]
            video = Path(entry["video_path"])
            if video.exists():
                dump(OUT / f"local_{vid}.json", video, detector,
                     {"set": "local", "id": vid})

    if WHICH in ("pushai", "both"):
        root = Path("data/external/pushai")
        vids = [(f, "correct") for f in sorted((root / "Correct sequence").glob("*.mp4"))] + \
               [(f, "wrong") for f in sorted((root / "Wrong sequence").glob("*.mp4"))]
        for video, group in vids:
            stem = video.stem.replace(" ", "_")
            dump(OUT / f"pushai_{group}_{stem}.json", video, detector,
                 {"set": "pushai", "group": group, "id": video.name})

    print("완료")


if __name__ == "__main__":
    main()

"""팔꿈치각 시계열 캐시 (영상별 증분 저장판).

1차 시도는 전체를 메모리에 모아 마지막에 한 번 저장해서, 2시간 실행이 멈췄을 때
진행분이 통째로 날아갔다. 여기서는 영상 하나 끝날 때마다 파일로 떨구고
이미 있는 파일은 건너뛴다(재시작 가능).

사용: py -3 cache_series2.py <출력폴더> [rehab|local|both]
"""
import csv
import json
import sys
from collections import defaultdict
from pathlib import Path

import cv2

sys.path.insert(0, str(Path.cwd()))
from ai.analysis.exercises.pushup import _elbow_angle  # noqa: E402
from ai.config import (  # noqa: E402
    VIDEO_FPS_FALLBACK, VIDEO_FPS_MAX, VIDEO_FPS_MIN, pose_model_for,
)
from ai.pose.detector import PoseDetector  # noqa: E402

# (스레드 수를 절반으로 줄였더니 1.2코어만 쓰며 5배 느려졌다 — 기본값을 쓴다.)

OUT = Path(sys.argv[1])
WHICH = sys.argv[2] if len(sys.argv) > 2 else "both"
# 진단에 필요한 영상만. PM_010(과다 카운트)은 추가 인물이 있어 트래커가 폭주,
# 4071프레임 중 3000에서 사실상 멈춰 제외했다. PM_119는 과소 카운트 사례로
# clip_27727791에서 특정한 'p95 오염' 기전을 외부 데이터로 확인하는 용도다.
# 순서 = 검증 가치 순. PM_031은 과다 카운트(11 vs 10) 위험 사례,
# PM_030/107/121은 현재 정확해서 회귀 확인용, 나머지는 과소 카운트 사례다.
REHAB_TARGETS = ["PM_119", "PM_031", "PM_030", "PM_107", "PM_121",
                 "PM_045", "PM_044", "PM_011", "PM_108"]


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
        angle = None if person is None else _elbow_angle(person)
        if angle is not None:
            out.append([idx, round(angle, 2)])
        idx += 1
        if idx % 500 == 0:
            print(f"    {video.stem[:9]} {idx}프레임", flush=True)
    cap.release()
    return fps, idx, out


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    detector = PoseDetector(pose_model_for("pushup"))

    if WHICH in ("rehab", "both"):
        segs = defaultdict(list)
        with Path("data/external/rehab24/Segmentation.csv").open(encoding="utf-8") as fh:
            for row in csv.DictReader(fh, delimiter=";"):
                if row["exercise_id"] == "3":
                    segs[row["video_id"]].append({
                        "rep": int(row["repetition_number"]),
                        "start": int(row["first_frame"]),
                        "end": int(row["last_frame"]),
                        "correct": row["correctness"] == "1",
                    })
        for vid in REHAB_TARGETS:
            dest = OUT / f"rehab_{vid}.json"
            if dest.exists():
                print(f"skip {vid}", flush=True)
                continue
            matches = list(Path("data/external/rehab24/Ex3").glob(f"{vid}*Camera17*.mp4"))
            if not matches:
                continue
            fps, frames, angles = series(matches[0], detector)
            dest.write_text(json.dumps({
                "set": "rehab", "id": vid, "fps": fps, "frames": frames,
                "angles": angles, "segments": segs.get(vid, []),
            }), encoding="utf-8")
            print(f"rehab {vid}: {len(angles)}/{frames}, 전문가 {len(segs[vid])} rep", flush=True)

    if WHICH in ("local", "both"):
        truth = json.loads(
            Path("data/pushup_rep_labels.json").read_text(encoding="utf-8"))["clips"]
        for name, count in sorted(truth.items()):
            dest = OUT / f"local_{name}.json"
            if dest.exists():
                print(f"skip {name}", flush=True)
                continue
            video = Path("data/videos/pushup_eval") / f"{name}.mp4"
            if not video.exists():
                continue
            fps, frames, angles = series(video, detector)
            dest.write_text(json.dumps({
                "set": "local", "id": name, "fps": fps, "frames": frames,
                "angles": angles, "expected_reps": count,
            }), encoding="utf-8")
            print(f"local {name}: {len(angles)}/{frames}, 정답 {count}", flush=True)

    print("완료")


if __name__ == "__main__":
    main()

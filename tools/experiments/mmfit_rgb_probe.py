"""MM-Fit RGB 원영상으로 YOLO 전체 경로 검증 (소형 워크아웃 선별).

39GB 전체는 디스크상 불가라, 관심 워크아웃(w17: 포즈 기반 검증의 최악 실패
2/9 포함, w19: 7-rep 세트 포함)만 받아 푸시업 구간을 잘라내고 원본은 지운다.
잘라낸 클립은 data/external/mmfit/clips/에 남아 재실행 가능하다.

사용:
  py -3 tools/experiments/mmfit_rgb_probe.py extract <w17>   # 구간 잘라내기
  py -3 tools/experiments/mmfit_rgb_probe.py run             # 엔진 실행·대조
출력: data/output/mmfit_rgb_evaluation.json
"""
import csv
import json
import sys
from pathlib import Path

import cv2

sys.path.insert(0, str(Path.cwd()))

ROOT = Path("data/external/mmfit")
CLIPS = ROOT / "clips"
OUT = Path("data/output/mmfit_rgb_evaluation.json")
MARGIN_FRAMES = 60  # 라벨 구간 앞뒤 2초(30fps) — 포즈 평가와 동일


def pushup_sets(workout: str):
    lab = ROOT / "mm-fit" / workout / f"{workout}_labels.csv"
    out = []
    with lab.open() as fh:
        for row in csv.reader(fh):
            if row[3] == "pushups":
                out.append((int(row[0]), int(row[1]), int(row[2])))
    return out


def extract(workout: str) -> None:
    video = ROOT / f"{workout}_rgb.mp4"
    CLIPS.mkdir(parents=True, exist_ok=True)
    cap = cv2.VideoCapture(str(video))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    print(f"{video.name}: {w}x{h} @ {fps:.1f}fps")
    for i, (s, e, reps) in enumerate(pushup_sets(workout), start=1):
        dest = CLIPS / f"{workout}_set{i}_r{reps}.mp4"
        if dest.exists():
            print(f"skip {dest.name}")
            continue
        start = max(0, s - MARGIN_FRAMES)
        cap.set(cv2.CAP_PROP_POS_FRAMES, start)
        writer = cv2.VideoWriter(str(dest), cv2.VideoWriter_fourcc(*"mp4v"),
                                 fps, (w, h))
        n = 0
        for _ in range(start, e + MARGIN_FRAMES):
            ok, frame = cap.read()
            if not ok:
                break
            writer.write(frame)
            n += 1
        writer.release()
        print(f"{dest.name}: {n}프레임")
    cap.release()


def run() -> None:
    from ai.engine import analyze_video
    from ai.pose.detector import PoseDetector
    from ai.config import pose_model_for

    detector = PoseDetector(pose_model_for("pushup"))
    results = []
    if OUT.exists():
        results = json.loads(OUT.read_text(encoding="utf-8"))
    done = {r["clip"] for r in results}
    for clip in sorted(CLIPS.glob("*.mp4")):
        if clip.name in done:
            continue
        truth = int(clip.stem.rsplit("_r", 1)[1])
        report = analyze_video(clip, "pushup", save_annotated=False,
                               detector=detector)
        results.append({
            "clip": clip.name, "truth": truth,
            "engine": report.rep_count,
            "partial": report.partial_rep_count,
            "video_codes": [i.code for i in report.video_issues],
            "body_baseline": report.body_line_baseline,
            "body_issues": [
                {"rep": i.rep_index, "code": i.code, "measured": i.measured}
                for i in report.issues
                if i.code in ("body_line_break", "excessive_body_line_break")
            ],
        })
        OUT.write_text(json.dumps(results, ensure_ascii=False, indent=1),
                       encoding="utf-8")
        print(f"{clip.name}: 엔진 {report.rep_count} / 정답 {truth} "
              f"(부분 {report.partial_rep_count}, 코드 "
              f"{[i.code for i in report.video_issues]})", flush=True)
    exact = sum(r["engine"] == r["truth"] for r in results)
    err = sum(abs(r["engine"] - r["truth"]) for r in results)
    total = sum(r["truth"] for r in results)
    print(f"\n정확 {exact}/{len(results)}, 총 {total} rep 절대 오차 {err} "
          f"(정확도 {max(0, 1 - err / total):.1%})")


if __name__ == "__main__":
    mode = sys.argv[1]
    if mode == "extract":
        extract(sys.argv[2])
    else:
        run()

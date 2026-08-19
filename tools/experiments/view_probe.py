"""푸시업 측면 판정 신규 지표 후보 실측.

기존 지표(어깨 x간격 ÷ 몸통 길이)는 측면/비측면 분포가 겹쳐 실패했다
(docs/PUSHUP_TUNING.md §7-B). 후보 지표들을 시점 라벨이 있는 영상 전체에서
프레임 단위로 재고 영상 중앙값을 남긴다.

후보:
  cur        기존: |어깨 x간격| ÷ 몸통 길이
  sh_torso_e 어깨 유클리드 간격 ÷ 몸통 길이
  hip_gap    |골반 x간격| ÷ 몸통 길이
  sh_body    어깨 유클리드 간격 ÷ 전신 길이(어깨중점→발목/무릎중점)
  horiz      몸통(어깨중점→엉덩이중점)의 수평 성분 비율 (측면 엎드림 ≈ 1)
  ank_gap    |발목 x간격| ÷ 전신 길이

실행: py -3 tools/experiments/view_probe.py [--stride 2]
출력: data/output/view_probe.json (영상별 지표 중앙값 + 시점 라벨)
"""
import argparse
import json
import math
import statistics
import sys
from pathlib import Path

import cv2

sys.path.insert(0, str(Path.cwd()))
from ai.config import pose_model_for  # noqa: E402
from ai.pose.detector import PoseDetector  # noqa: E402
from ai.pose.keypoints import KP  # noqa: E402

OUT = Path("data/output/view_probe.json")

# (경로, 시점 라벨). 시점 근거: pushup_labels.json(16 side), §7-0 육안 분류
# (clip_4754030/31/32·7319949 = 정면·사선), MM-Fit w17/w19 = 육안 확인 측면.
def targets() -> list[tuple[Path, str]]:
    import json as _json
    labeled = _json.load(open("data/pushup_labels.json", encoding="utf-8"))
    out = [(Path(x["video_path"]), x["view"]) for x in labeled]
    for cid in ("4754030", "4754031", "4754032", "7319949"):
        out.append((Path(f"data/videos/pushup_eval/clip_{cid}.mp4"), "nonside"))
    for clip in sorted(Path("data/external/mmfit/clips").glob("*.mp4")):
        out.append((clip, "side"))
    return out


def _dist(a, b) -> float:
    return math.hypot(a.x - b.x, a.y - b.y)


def _mid(a, b) -> tuple[float, float]:
    return ((a.x + b.x) / 2, (a.y + b.y) / 2)


def frame_metrics(person) -> dict[str, float]:
    m: dict[str, float] = {}
    ls, rs = person[KP.LEFT_SHOULDER], person[KP.RIGHT_SHOULDER]
    lh, rh = person[KP.LEFT_HIP], person[KP.RIGHT_HIP]
    la, ra = person[KP.LEFT_ANKLE], person[KP.RIGHT_ANKLE]
    lk, rk = person[KP.LEFT_KNEE], person[KP.RIGHT_KNEE]

    torso = []
    if ls.visible and lh.visible:
        torso.append(_dist(ls, lh))
    if rs.visible and rh.visible:
        torso.append(_dist(rs, rh))
    torso_len = sum(torso) / len(torso) if torso else None

    sh_pair = ls.visible and rs.visible
    hip_pair = lh.visible and rh.visible

    if torso_len and sh_pair:
        m["cur"] = abs(ls.x - rs.x) / torso_len
        m["sh_torso_e"] = _dist(ls, rs) / torso_len
    if torso_len and hip_pair:
        m["hip_gap"] = abs(lh.x - rh.x) / torso_len

    # 전신 길이: 어깨중점 → (발목 보이면 발목, 아니면 무릎) 중점.
    far = None
    if la.visible and ra.visible:
        far = _mid(la, ra)
    elif la.visible:
        far = (la.x, la.y)
    elif ra.visible:
        far = (ra.x, ra.y)
    elif lk.visible and rk.visible:
        far = _mid(lk, rk)
    elif lk.visible:
        far = (lk.x, lk.y)
    elif rk.visible:
        far = (rk.x, rk.y)
    if sh_pair and far is not None:
        smid = _mid(ls, rs)
        body = math.hypot(smid[0] - far[0], smid[1] - far[1])
        if body > 1e-6:
            m["sh_body"] = _dist(ls, rs) / body
            if la.visible and ra.visible:
                m["ank_gap"] = abs(la.x - ra.x) / body

    if sh_pair and hip_pair:
        smid, hmid = _mid(ls, rs), _mid(lh, rh)
        seg = math.hypot(smid[0] - hmid[0], smid[1] - hmid[1])
        if seg > 1e-6:
            m["horiz"] = abs(smid[0] - hmid[0]) / seg
    return m


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stride", type=int, default=2)
    args = ap.parse_args()

    detector = PoseDetector(pose_model_for("pushup"))
    rows = []
    if OUT.exists():
        rows = json.loads(OUT.read_text(encoding="utf-8"))
    done = {r["video"] for r in rows}
    for path, view in targets():
        if path.name in done:
            continue
        if not path.exists():
            print(f"없음: {path}")
            continue
        cap = cv2.VideoCapture(str(path))
        samples: dict[str, list[float]] = {}
        idx = 0
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            if idx % args.stride == 0:
                person = detector.detect(frame)
                if person is not None:
                    for k, v in frame_metrics(person).items():
                        samples.setdefault(k, []).append(v)
            idx += 1
        cap.release()
        row = {"video": path.name, "view": view,
               "frames_sampled": idx // args.stride}
        for k, vals in samples.items():
            if len(vals) >= 10:
                row[k] = round(statistics.median(vals), 3)
                row[f"{k}_n"] = len(vals)
        rows.append(row)
        OUT.write_text(json.dumps(rows, ensure_ascii=False, indent=1),
                       encoding="utf-8")
        shown = {k: row[k] for k in
                 ("cur", "sh_torso_e", "hip_gap", "sh_body", "horiz", "ank_gap")
                 if k in row}
        print(f"{path.name} [{view}] {shown}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

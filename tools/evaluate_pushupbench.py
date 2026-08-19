"""PushupBench 푸시업 계열 클립으로 rep 카운트 외부 검증 (검증 전용).

데이터: huggingface.co/datasets/anonymousatom/pushupbench (CC BY 4.0).
VLM용 반복 카운트 벤치마크 227클립 중 푸시업 계열(팔꿈치 굽힘 왕복이 1 rep인
변형)만 쓴다 — 표준/무릎/박스/벽/토탭. 정답은 metadata.json의 `count` 목록이며
복수 값은 "어느 것이든 정답"으로 취급한다(시작·끝 경계의 모호성 반영).

주의:
- 이 데이터는 촬영 각도가 통제되지 않는다(홈트 구도). 측면 전용 전제가 깨진
  클립은 `not_side_view` 코드와 함께 참고 성적으로만 본다.
- 스쿼트·다른 운동 클립은 우리 엔진 대상이 아니므로 쓰지 않는다.

실행: py -3 -m tools.evaluate_pushupbench
출력: data/output/pushupbench_evaluation.json
"""
from __future__ import annotations

import json
from pathlib import Path

from ai.config import pose_model_for
from ai.engine import analyze_video
from ai.pose.detector import PoseDetector

ROOT = Path("data/external/pushupbench")
OUT = Path("data/output/pushupbench_evaluation.json")

# metadata.json에서 푸시업 계열로 판단한 클립(이름에 push 포함 중 팔꿈치
# 왕복 운동인 것). 'stting tricep push'는 앉은 삼두 운동이라 제외.
TARGETS = {
    "14c2c3f4_0447_push up toe tap_[14-13-15].mp4": "push up toe tap",
    "1e6a72cd_0814_wall push_[10].mp4": "wall push",
    "36f0d07e_0716_box push-ups_[11].mp4": "box push-ups",
    "5e3a8d78_0514_push up (on knees)_[12].mp4": "push up (on knees)",
}


def main() -> None:
    meta = {e["video_path"]: e for e in json.loads(
        (ROOT / "metadata.json").read_text(encoding="utf-8"))}
    detector = PoseDetector(pose_model_for("pushup"))
    rows = []
    for fname, label in TARGETS.items():
        entry = meta[fname]
        video = ROOT / "videos" / fname
        report = analyze_video(video, "pushup", save_annotated=False, detector=detector)
        accepted = entry["count"]
        engine = report.rep_count
        err = min(abs(engine - c) for c in accepted)
        rows.append({
            "clip": fname,
            "exercise": label,
            "accepted_counts": accepted,
            "engine": engine,
            "partial_reps": report.partial_rep_count,
            "abs_err": err,
            "exact": err == 0,
            "video_codes": [i.code for i in report.video_issues],
            "camera_view": report.camera_view,
        })
        print(f"{label:<22} 엔진 {engine} / 정답 {accepted} "
              f"(오차 {err}) codes={rows[-1]['video_codes']}", flush=True)

    total_truth = sum(min(r["accepted_counts"]) for r in rows)
    summary = {
        "dataset": {
            "name": "PushupBench (pushup-family subset)",
            "source": "huggingface.co/datasets/anonymousatom/pushupbench",
            "license": "CC BY 4.0",
            "holdout": "푸시업 파라미터 결정에 이 데이터는 일절 사용되지 않음",
        },
        "clips": len(rows),
        "exact": sum(r["exact"] for r in rows),
        "abs_err_total": sum(r["abs_err"] for r in rows),
        "count_accuracy_lower_bound": round(
            1 - sum(r["abs_err"] for r in rows) / total_truth, 4),
        "rows": rows,
    }
    OUT.write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()

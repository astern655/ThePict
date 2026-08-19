"""PushAI 클립 전수 분석 — 몸통 이탈각 측정 기록 수집 (검증 전용).

데이터: github.com/Kathit873/PushAI (라이선스 미표기·출처 불명 — 재배포·제품
포함 금지, 로컬 검증 전용). 측면·단일 카메라·단일 피험자의 correct/wrong
푸시업 클립. wrong에는 몸통 결함(엉덩이 솟음·완전 낙하) 시연이 포함돼 있어,
푸시업 몸통 판정 중단(docs/PUSHUP_TUNING.md §9) 재개 조건 (c)의 첫 실영상
YOLO 공간 근거 후보다.

실행: py -3 tools/experiments/pushai_bodyline.py [출력경로]
출력(기본): data/output/pushai_bodyline.json — 클립별 rep 수·top/최저점 이탈각·판정

2026-08-14: 기준선 캘리브레이션 판정 도입 후 재실행용으로 기록 항목 확장
(body_line_baseline, top_body_delta, body_issues). 출력 경로를 바꿔 돌리면
구판 결과(pushai_bodyline.json)를 보존한 채 신판을 비교할 수 있다.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from ai.engine import analyze_video
from ai.pose.detector import PoseDetector
from ai.config import pose_model_for

ROOT = Path("data/external/pushai")
OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("data/output/pushai_bodyline.json")

detector = PoseDetector(pose_model_for("pushup"))
results = []
existing = {}
if OUT.exists():
    existing = {r["clip"]: r for r in json.loads(OUT.read_text(encoding="utf-8"))}

vids = [(f, "correct") for f in sorted((ROOT / "Correct sequence").glob("*.mp4"))] + \
       [(f, "wrong") for f in sorted((ROOT / "Wrong sequence").glob("*.mp4"))]
for i, (video, group) in enumerate(vids, start=1):
    clip_id = f"{group}/{video.name}"
    if clip_id in existing:
        results.append(existing[clip_id])
        continue
    try:
        report = analyze_video(video, "pushup", save_annotated=False, detector=detector)
    except Exception as exc:  # 한 클립 실패가 전체를 막지 않게
        results.append({"clip": clip_id, "error": str(exc)})
        continue
    results.append({
        "clip": clip_id,
        "group": group,
        "rep_count": report.rep_count,
        "partial_reps": report.partial_rep_count,
        "video_codes": [i.code for i in report.video_issues],
        "body_line_baseline": report.body_line_baseline,
        "body_issues": [
            {"rep": i.rep_index, "code": i.code, "measured": i.measured}
            for i in report.issues
            if i.code in ("body_line_break", "excessive_body_line_break")
        ],
        "reps": [
            {
                "rep": r.rep_index,
                "bottom_angle": r.bottom_angle,
                "top_body_dev": r.top_body_line_dev,
                "top_body_delta": r.top_body_line_delta,
                "bottom_body_dev": r.bottom_body_line_dev,
            }
            for r in report.reps
        ],
    })
    OUT.write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"[{i}/{len(vids)}] {clip_id}: rep {report.rep_count}", flush=True)

OUT.write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")
print(f"완료: {len(results)}클립 → {OUT}")

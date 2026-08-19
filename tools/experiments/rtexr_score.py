"""RTExR 검증 채점: 엔진 vs 사람 라벨(카운트·시점).

카운트: 실영상 40편(kaggle·similar·mytest)만 — syn은 블라인드가 깨져 제외.
게이트: 시점 라벨 60편 — side는 반려가 없어야 하고 nonside는 있어야 한다.
        oblique(강한 사선)·partial(프레임 이탈)은 경계라 채점 밖(기록만).

실행: py -3 tools/experiments/rtexr_score.py
출력: data/output/rtexr_evaluation.json
"""
import json
from pathlib import Path

probe = {r["video"].removesuffix(".mp4"): r
         for r in json.loads(Path("data/output/rtexr_probe.json").read_text(encoding="utf-8"))}
counts = json.loads(Path("data/external/rtexr/count_labels.json").read_text(encoding="utf-8"))
views = json.loads(Path("data/external/rtexr/view_labels.json").read_text(encoding="utf-8"))

# --- 카운트 채점 ---------------------------------------------------------
rows = []
exact = abs_err = truth_total = 0
for vid, lab in counts.items():
    if vid.startswith("_") or vid not in probe:
        continue
    eng = probe[vid]["engine"]
    accept = lab["accept"]
    hit = eng in accept
    err = min(abs(eng - a) for a in accept)
    mid = accept[len(accept) // 2]
    exact += hit
    abs_err += err
    truth_total += mid
    rows.append({"video": vid, "engine": eng, "accept": accept, "hit": hit,
                 "err": err, "confidence": lab["confidence"],
                 "codes": probe[vid]["video_codes"]})

# --- 게이트 채점 ---------------------------------------------------------
gate = {"side": {"total": 0, "rejected": 0, "rejected_list": []},
        "nonside": {"total": 0, "rejected": 0, "missed_list": []},
        "oblique": {"total": 0, "rejected": 0},
        "partial": {"total": 0, "rejected": 0}}
for vid, view in views.items():
    if vid.startswith("_") or vid not in probe:
        continue
    codes = probe[vid]["video_codes"]
    rejected = "not_side_view" in codes
    g = gate[view]
    g["total"] += 1
    g["rejected"] += rejected
    if view == "side" and rejected:
        g["rejected_list"].append(vid)
    if view == "nonside" and not rejected:
        g["missed_list"].append(vid)

summary = {
    "count": {
        "clips": len(rows), "exact_in_accept": exact,
        "exact_rate": round(exact / len(rows), 4) if rows else None,
        "abs_err_total": abs_err,
        "count_accuracy": round(max(0.0, 1 - abs_err / truth_total), 4)
        if truth_total else None,
    },
    "gate": {
        "side_false_reject": f"{gate['side']['rejected']}/{gate['side']['total']}",
        "side_false_reject_list": gate["side"]["rejected_list"],
        "nonside_caught": f"{gate['nonside']['rejected']}/{gate['nonside']['total']}",
        "nonside_missed_list": gate["nonside"]["missed_list"],
        "oblique_rejected": f"{gate['oblique']['rejected']}/{gate['oblique']['total']}",
        "partial_rejected": f"{gate['partial']['rejected']}/{gate['partial']['total']}",
    },
}
print(json.dumps(summary, ensure_ascii=False, indent=1))
Path("data/output/rtexr_evaluation.json").write_text(
    json.dumps({"summary": summary, "count_rows": rows, "gate": gate},
               ensure_ascii=False, indent=1), encoding="utf-8")
miss = [r for r in rows if not r["hit"]]
print("\n빗나간 클립:")
for r in miss:
    print(f"  {r['video']}: 엔진 {r['engine']} / 허용 {r['accept']} "
          f"({r['confidence']}) 코드 {r['codes']}")

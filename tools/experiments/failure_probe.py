"""실패 클립이 파라미터로 고쳐지는지, 고치면 무엇이 깨지는지 조사한다.

격자 탐색이 '기준선을 못 넘는다'로 끝났을 때, 그것이
(a) 해당 클립이 어떤 설정으로도 안 고쳐지는 것인지
(b) 고쳐지지만 다른 클립을 깨뜨리는 트레이드오프인지
를 가른다. 대응 방향이 완전히 다르므로 반드시 구분해야 한다.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from rep_lab import count_reps  # noqa: E402

BASE = dict(down_ratio=0.35, up_ratio=0.70, min_span=25.0, window=7)
TARGETS = ["clip_27727791", "clip_5802475"]

series_dir = Path(sys.argv[1])
items = {}
for p in sorted(series_dir.glob("local_*.json")):
    it = json.loads(p.read_text(encoding="utf-8"))
    items[it["id"]] = it

# 넓은 격자: 이 클립을 고치는 설정이 하나라도 있는가
grid = []
for up in [x / 100 for x in range(40, 86, 5)]:
    for down in [x / 100 for x in range(15, 51, 5)]:
        for win in (3, 5, 7, 9, 13):
            for peak in (False, True):
                grid.append({**BASE, "up_ratio": up, "down_ratio": down,
                             "window": win, "peak_ref": peak})

print(f"격자 {len(grid)}개 설정으로 조사\n")
for tid in TARGETS:
    it = items[tid]
    truth = it["expected_reps"]
    base_n, _ = count_reps(it["angles"], it["fps"], **BASE)
    fixes = []
    for p in grid:
        n, _ = count_reps(it["angles"], it["fps"], **p)
        if n == truth:
            fixes.append(p)
    print(f"{tid}: 기준선 {base_n} / 정답 {truth} → 고치는 설정 {len(fixes)}/{len(grid)}개")
    if not fixes:
        print("   ⇒ 어떤 파라미터 조합으로도 못 고침 (지표/신호 한계)")
        continue
    # 고치는 설정 중 나머지 클립을 가장 덜 깨뜨리는 것
    best = None
    for p in fixes:
        broken = []
        for other_id, other in items.items():
            if other_id == tid:
                continue
            n, _ = count_reps(other["angles"], other["fps"], **p)
            if n != other["expected_reps"]:
                broken.append(other_id)
        if best is None or len(broken) < len(best[1]):
            best = (p, broken)
    extra = {k: v for k, v in best[0].items() if BASE.get(k) != v}
    print(f"   ⇒ 고치는 최선 설정 {extra}")
    print(f"      대신 깨지는 클립 {len(best[1])}개: {best[1]}")

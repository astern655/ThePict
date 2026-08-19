"""후보 파라미터를 전 클립에 적용해 기준선과 클립 단위로 대조한다."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from rep_lab import count_reps  # noqa: E402

BASE = dict(down_ratio=0.35, up_ratio=0.70, min_span=25.0, window=7)
CAND = dict(down_ratio=0.40, up_ratio=0.65, min_span=25.0, window=5)

series_dir = Path(sys.argv[1])
print(f"{'클립':<20}{'정답':>5}{'기준선':>7}{'후보':>6}   변화")
b_ok = c_ok = 0
b_err = c_err = 0
for p in sorted(series_dir.glob("local_*.json")):
    it = json.loads(p.read_text(encoding="utf-8"))
    t = it["expected_reps"]
    b, _ = count_reps(it["angles"], it["fps"], **BASE)
    c, _ = count_reps(it["angles"], it["fps"], **CAND)
    b_ok += b == t
    c_ok += c == t
    b_err += abs(b - t)
    c_err += abs(c - t)
    mark = ""
    if (b == t) and (c != t):
        mark = "  ← 후보가 깨뜨림"
    elif (b != t) and (c == t):
        mark = "  ← 후보가 고침"
    print(f"{it['id']:<20}{t:>5}{b:>7}{c:>6}{mark}")
print(f"\n기준선 {b_ok}/16 오차 {b_err} / 후보 {c_ok}/16 오차 {c_err}")

rehab = sorted(series_dir.glob("rehab_*.json"))
if rehab:
    print(f"\n[외부] REHAB {len(rehab)}편")
    for p in rehab:
        it = json.loads(p.read_text(encoding="utf-8"))
        t = len(it["segments"])
        b, _ = count_reps(it["angles"], it["fps"], **BASE)
        c, _ = count_reps(it["angles"], it["fps"], **CAND)
        print(f"  {it['id']}: 정답 {t} / 기준선 {b} / 후보 {c}")
else:
    print("\n[외부] REHAB 캐시 없음 — 외부 확인 불가")

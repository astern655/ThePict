"""과소/과다 카운트 영상의 각도 시계열을 텍스트 스파크라인으로 진단한다."""
import json
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path.cwd()))
from rep_lab import count_reps, median_smooth  # noqa: E402

path = Path(sys.argv[1])
item = json.loads(path.read_text(encoding="utf-8"))
angles = item["angles"]
fps = item["fps"]
raw = [a for _, a in angles]
smooth = median_smooth(raw, 7)

q = statistics.quantiles(smooth, n=100)
low, high = q[4], q[94]
span = high - low
down_t = low + 0.35 * span
up_t = low + 0.70 * span
print(f"{item['id']}  fps={fps}  측정프레임 {len(angles)}/{item['frames']}")
print(f"  p5={low:.1f} p95={high:.1f} 폭={span:.1f}  →  DOWN<{down_t:.1f}  UP>{up_t:.1f}")
truth = item.get("expected_reps") or len(item.get("segments", []))
n, reps = count_reps(angles, fps)
print(f"  엔진 {n} rep / 정답 {truth}")
for r in reps:
    print(f"    rep {r['start']}~{r['end']} 최저 {r['min_angle']}")

# 0.25초 간격 스파크라인: 각 구간의 최저 평활각
step = max(1, int(round(fps * 0.25)))
print(f"\n  0.25초 간격 최저 평활각 (U=UP선 위, d=DOWN선 아래):")
line_v, line_m = [], []
for i in range(0, len(smooth), step):
    chunk = smooth[i:i + step]
    v = min(chunk)
    line_v.append(f"{v:3.0f}")
    line_m.append("d" if v < down_t else ("U" if v > up_t else "."))
for i in range(0, len(line_v), 24):
    t0 = angles[i * step][0] / fps if i * step < len(angles) else 0
    print(f"   {t0:5.1f}s " + " ".join(line_v[i:i + 24]))
    print(f"         " + "   ".join(line_m[i:i + 24]))

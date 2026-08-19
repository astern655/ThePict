"""결합 세트(로컬+REHAB)에서 leave-one-video-out으로 후보 선택의 일반화를 본다.

joint_search.py가 고른 최선 후보는 216개를 같은 데이터로 평가해 고른 값이라
낙관 편향이 있다. 여기서는 영상 하나를 빼고 나머지에서 후보를 고른 뒤,
보지 않은 그 영상에 적용해 오차를 누적한다.
"""
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from joint_search import BASE, load, score  # noqa: E402
from rep_lab import count_reps  # noqa: E402


def candidates():
    out = []
    for win in (5, 7, 9, 11, 13, 15):
        for up in (0.55, 0.60, 0.65, 0.70, 0.75, 0.80):
            for down in (0.25, 0.30, 0.35, 0.40, 0.45):
                out.append({**BASE, "window": win, "up_ratio": up, "down_ratio": down})
    for win in (7, 9, 13):
        for up in (0.60, 0.65, 0.70, 0.75):
            for down in (0.30, 0.35, 0.40):
                out.append({**BASE, "peak_ref": True, "window": win,
                            "up_ratio": up, "down_ratio": down})
    return out


def main():
    local, rehab = load(Path(sys.argv[1]))
    items = local + rehab
    cands = candidates()
    print(f"영상 {len(items)}편 / 후보 {len(cands)}개\n")

    base = score(items, BASE)
    print(f"[기준선] 정확 {base['exact']}/{base['n']} 오차 {base['err']} 최악 {base['worst']}")

    fixed = dict(down_ratio=0.45, up_ratio=0.60, min_span=25.0, window=13)
    fx = score(items, fixed)
    print(f"[전체최적] 정확 {fx['exact']}/{fx['n']} 오차 {fx['err']} 최악 {fx['worst']}"
          f"  (같은 데이터로 고름 — 낙관 편향)\n")

    loo_err = loo_exact = loo_worst = 0
    picks = Counter()
    for held in items:
        rest = [x for x in items if x["id"] != held["id"]]
        best = min(cands, key=lambda p: (score(rest, p)["err"], -score(rest, p)["exact"]))
        n, _ = count_reps(held["angles"], held["fps"], **best)
        d = abs(n - held["truth"])
        loo_err += d
        loo_exact += d == 0
        loo_worst = max(loo_worst, d)
        key = (f"w{best['window']} up{best['up_ratio']} dn{best['down_ratio']}"
               f"{' peak' if best.get('peak_ref') else ''}")
        picks[key] += 1
    print(f"[LOO] 정확 {loo_exact}/{len(items)} 오차 {loo_err} 최악 {loo_worst}")
    print(f"      기준선 대비 오차 {base['err']} → {loo_err}")
    for k, v in picks.most_common(5):
        print(f"      {v:>2}회 선택: {k}")


if __name__ == "__main__":
    main()

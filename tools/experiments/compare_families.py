"""후보 계열 3종을 두 세트에서 영상 단위로 비교한다.

총오차만 보면 한 편의 파국적 실패가 가려진다. 최악 오차와 영상별 변화를
함께 봐야 '평균은 좋아졌는데 특정 사용자에겐 크게 틀리는' 선택을 피할 수 있다.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from joint_search import BASE, load, score  # noqa: E402

FAMILIES = {
    "기준선": BASE,
    "비율+윈도13": {**BASE, "down_ratio": 0.45, "up_ratio": 0.60, "window": 13},
    "봉우리기준": {**BASE, "down_ratio": 0.40, "peak_ref": True},
}

local, rehab = load(Path(sys.argv[1]))
items = local + rehab

print(f"{'계열':<14}{'로컬정확':>9}{'REHAB정확':>10}{'총오차':>8}{'최악':>6}")
res = {}
for name, p in FAMILIES.items():
    sl, sr = score(local, p), score(rehab, p)
    res[name] = (sl, sr)
    print(f"{name:<14}{sl['exact']:>6}/{sl['n']:<2}{sr['exact']:>7}/{sr['n']:<2}"
          f"{sl['err'] + sr['err']:>8}{max(sl['worst'], sr['worst']):>6}")

print(f"\n{'영상':<18}{'정답':>5}" + "".join(f"{n:>13}" for n in FAMILIES))
for it in items:
    row = f"{it['id']:<18}{it['truth']:>5}"
    vals = []
    for name in FAMILIES:
        sl, sr = res[name]
        per = sl["per"] if it["id"] in sl["per"] else sr["per"]
        vals.append(per[it["id"]][0])
    if all(v == it["truth"] for v in vals):
        continue  # 모든 계열이 맞춘 영상은 생략
    row += "".join(f"{v:>13}" for v in vals)
    print(row)

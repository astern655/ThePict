"""로컬 + REHAB 두 세트를 **함께** 놓고 rep 카운트 파라미터를 탐색한다.

로컬만 보고 고른 후보가 REHAB PM_121을 11→23으로 파괴한 사건 이후 만든 도구다.
두 실패 방향(과소·과다)이 서로 반대라 한쪽만 보면 반드시 다른 쪽이 깨진다.

평가 기준:
  - 1순위: 두 세트 총 절대오차
  - 제약: 로컬 정확 편수가 기준선(14/16) 미만이면 탈락
  - 참고: REHAB 최악 영상 오차(한 영상이 파국적으로 틀리는 것을 막는다)
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from rep_lab import count_reps  # noqa: E402

BASE = dict(down_ratio=0.35, up_ratio=0.70, min_span=25.0, window=7)


def load(series_dir: Path):
    local, rehab = [], []
    for p in sorted(series_dir.glob("local_*.json")):
        it = json.loads(p.read_text(encoding="utf-8"))
        it["truth"] = it["expected_reps"]
        local.append(it)
    for p in sorted(series_dir.glob("rehab_*.json")):
        it = json.loads(p.read_text(encoding="utf-8"))
        it["truth"] = len(it["segments"])
        rehab.append(it)
    return local, rehab


def score(items, params):
    exact = err = worst = 0
    per = {}
    for it in items:
        n, _ = count_reps(it["angles"], it["fps"], **params)
        d = abs(n - it["truth"])
        exact += d == 0
        err += d
        worst = max(worst, d)
        per[it["id"]] = (n, it["truth"])
    return {"exact": exact, "n": len(items), "err": err, "worst": worst, "per": per}


def main():
    local, rehab = load(Path(sys.argv[1]))
    print(f"로컬 {len(local)}편 / REHAB {len(rehab)}편\n")

    bl, br = score(local, BASE), score(rehab, BASE)
    print(f"[기준선] 로컬 {bl['exact']}/{bl['n']} 오차 {bl['err']} | "
          f"REHAB {br['exact']}/{br['n']} 오차 {br['err']} 최악 {br['worst']} | "
          f"총오차 {bl['err'] + br['err']}\n")

    cands = []
    for win in (5, 7, 9, 11, 13, 15):
        for up in (0.55, 0.60, 0.65, 0.70, 0.75, 0.80):
            for down in (0.25, 0.30, 0.35, 0.40, 0.45):
                cands.append({**BASE, "window": win, "up_ratio": up, "down_ratio": down})
    for win in (7, 9, 13):
        for up in (0.60, 0.65, 0.70, 0.75):
            for down in (0.30, 0.35, 0.40):
                cands.append({**BASE, "peak_ref": True, "window": win,
                              "up_ratio": up, "down_ratio": down})

    rows = []
    for p in cands:
        sl, sr = score(local, p), score(rehab, p)
        rows.append({
            "p": p, "l": sl, "r": sr,
            "total": sl["err"] + sr["err"],
            "exact": sl["exact"] + sr["exact"],
        })
    # 로컬을 기준선 아래로 떨어뜨리는 설정은 탈락
    ok = [r for r in rows if r["l"]["exact"] >= bl["exact"]]
    ok.sort(key=lambda r: (r["total"], -r["exact"], r["r"]["worst"]))

    print(f"[상위 후보] 로컬 {bl['exact']}/16 이상 유지 조건 통과 {len(ok)}/{len(rows)}개")
    print(f"{'총오차':>6}{'정확':>7}{'REHAB최악':>10}  파라미터")
    seen = set()
    for r in ok[:10]:
        extra = tuple(sorted((k, v) for k, v in r["p"].items() if BASE.get(k) != v))
        if extra in seen:
            continue
        seen.add(extra)
        print(f"{r['total']:>6}{r['exact']:>4}/{r['l']['n'] + r['r']['n']:<2}"
              f"{r['r']['worst']:>10}  {dict(extra) or '기준선과 동일'}")

    if ok:
        best = ok[0]
        print("\n[최선 후보 상세]")
        extra = {k: v for k, v in best["p"].items() if BASE.get(k) != v}
        print(f"  파라미터: {extra or '기준선과 동일'}")
        for name, s, b in (("로컬", best["l"], bl), ("REHAB", best["r"], br)):
            print(f"  {name}: {s['exact']}/{s['n']} 오차 {s['err']} "
                  f"(기준선 {b['exact']}/{b['n']} 오차 {b['err']})")
            for cid, (n, t) in s["per"].items():
                bn = b["per"][cid][0]
                if n != t or bn != t:
                    flag = "→개선" if abs(n - t) < abs(bn - t) else (
                        "→악화" if abs(n - t) > abs(bn - t) else "")
                    print(f"      {cid}: 정답 {t} 기준선 {bn} 후보 {n} {flag}")


if __name__ == "__main__":
    main()

"""rep 카운트 파라미터 격자 탐색 (오프라인, 캐시 기반).

평가 규칙:
  - 로컬 세트를 깎지 않는 것이 1순위(현재 14/16, 카운트 정확도 96.4%).
  - 리브-원-클립-아웃으로 '한 편에 맞춘 값'을 걸러낸다.
  - REHAB 캐시가 있으면 외부 확인으로 함께 출력한다(튜닝 대상 아님).

사용: py -3 tools/experiments/grid_search.py data/output/series
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
        local.append(json.loads(p.read_text(encoding="utf-8")))
    for p in sorted(series_dir.glob("rehab_*.json")):
        rehab.append(json.loads(p.read_text(encoding="utf-8")))
    return local, rehab


def score(items, params, truth_key):
    exact = err = total = 0
    detail = []
    for it in items:
        n, _ = count_reps(it["angles"], it["fps"], **params)
        t = it[truth_key] if truth_key in it else len(it["segments"])
        exact += n == t
        err += abs(n - t)
        total += t
        detail.append((it["id"], n, t))
    return {
        "exact": exact, "n": len(items), "abs_err": err,
        "count_acc": max(0.0, 1 - err / total) if total else 0.0,
        "detail": detail,
    }


def main():
    series_dir = Path(sys.argv[1])
    local, rehab = load(series_dir)
    print(f"로컬 {len(local)}편 / REHAB {len(rehab)}편\n")

    base = score(local, BASE, "expected_reps")
    print(f"[기준선] 정확 {base['exact']}/{base['n']}  "
          f"카운트 정확도 {base['count_acc']:.1%}  오차합 {base['abs_err']}")
    for cid, n, t in base["detail"]:
        if n != t:
            print(f"    {cid}: 엔진 {n} / 정답 {t}")
    print()

    # --- 후보 격자 ---------------------------------------------------------
    # 평활 윈도(window)를 반드시 포함한다. 1차 탐색에서 이 축을 빼먹어
    # "기준선을 못 넘는다"는 잘못된 결론을 낼 뻔했다(failure_probe.py가 잡아냄).
    cands = []
    for win in (5, 7, 9, 13):
        for up in (0.50, 0.55, 0.60, 0.65, 0.70, 0.75):
            for down in (0.25, 0.30, 0.35, 0.40, 0.45):
                cands.append(("비율+윈도", {**BASE, "window": win,
                                         "up_ratio": up, "down_ratio": down}))
    for hi in (89, 92, 94):
        for win in (7, 13):
            for up in (0.55, 0.60, 0.70):
                cands.append(("상단백분위", {**BASE, "hi_pct": hi,
                                        "window": win, "up_ratio": up}))
    for win in (7, 13):
        for up in (0.55, 0.60, 0.70):
            for down in (0.30, 0.35, 0.40):
                cands.append(("봉우리기준", {**BASE, "peak_ref": True, "window": win,
                                        "up_ratio": up, "down_ratio": down}))

    results = []
    for tag, p in cands:
        s = score(local, p, "expected_reps")
        results.append((s["exact"], -s["abs_err"], tag, p, s))
    results.sort(key=lambda r: (-r[0], r[1]))

    print("[상위 후보] (로컬 기준)")
    print(f"{'방식':<10}{'정확':>6}{'오차':>6}{'정확도':>9}  파라미터")
    seen = set()
    for exact, negerr, tag, p, s in results[:12]:
        key = (exact, -negerr, tag)
        if key in seen:
            continue
        seen.add(key)
        extra = {k: v for k, v in p.items() if BASE.get(k) != v}
        print(f"{tag:<10}{s['exact']:>4}/{s['n']:<2}{s['abs_err']:>6}"
              f"{s['count_acc']:>9.1%}  {extra}")

    # --- 리브-원-클립-아웃: 후보 선택 자체의 과적합 확인 --------------------
    print("\n[LOO CV] 각 클립을 뺀 나머지에서 최적 후보를 고른 뒤 그 클립에 적용")
    loo_exact = loo_err = 0
    picks = {}
    for held in local:
        rest = [x for x in local if x["id"] != held["id"]]
        scored = [(score(rest, p, "expected_reps"), tag, p) for tag, p in cands]
        s, tag, p = max(scored, key=lambda t: (t[0]["exact"], -t[0]["abs_err"]))
        n, _ = count_reps(held["angles"], held["fps"], **p)
        loo_exact += n == held["expected_reps"]
        loo_err += abs(n - held["expected_reps"])
        key = f"{tag} w{p['window']} up{p['up_ratio']} dn{p['down_ratio']}"
        picks[key] = picks.get(key, 0) + 1
    print(f"  LOO 정확 {loo_exact}/{len(local)} 오차 {loo_err}  "
          f"(기준선 {base['exact']}/{base['n']} 오차 {base['abs_err']})")
    for k, v in sorted(picks.items(), key=lambda kv: -kv[1]):
        print(f"    {v:>2}회 선택: {k}")

    if rehab:
        print("\n[외부 확인] REHAB (튜닝에 쓰지 않음)")
        for tag, p in [("기준선", BASE)] + [(r[2], r[3]) for r in results[:3]]:
            s = score(rehab, p, "__seg__")
            extra = {k: v for k, v in p.items() if BASE.get(k) != v}
            print(f"  {tag:<10} 정확 {s['exact']}/{s['n']} 오차 {s['abs_err']}  "
                  f"{s['detail']}  {extra}")


if __name__ == "__main__":
    main()

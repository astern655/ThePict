"""몸통 캘리브레이션 판정 오프라인 실험대.

cache_pushup_body.py가 만든 프레임 캐시([idx, 팔꿈치각, 이탈각, 방향])로
프로덕션 몸통 판정 경로(top 수집 → 기준선 → 델타)를 재현하고,
기준선 정의·δ 임계를 YOLO 없이 격자 비교한다.

용어:
  부호 이탈각 = +처짐(엉덩이가 선 아래) / −솟음. 방향 불명 프레임은 제외.
  top 프레임  = 평활 팔꿈치각 > UP 임계(영상별 적응값)인 프레임.
  캘리브레이션 구간 = 첫 dip(평활각이 UP 임계 아래로 처음 내려감) 이전.

실행: py -3 tools/experiments/body_lab.py <캐시폴더> [diag|grid]
"""
import json
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path.cwd()))
from rep_lab import count_reps, median_smooth  # noqa: E402

from ai.config import (  # noqa: E402
    PUSHUP_ADAPTIVE_DOWN_RATIO, PUSHUP_ADAPTIVE_MIN_SPAN, PUSHUP_ADAPTIVE_UP_RATIO,
    PUSHUP_ANGLE_SMOOTH_WINDOW, PUSHUP_ELBOW_DOWN_ANGLE, PUSHUP_ELBOW_UP_ANGLE,
    PUSHUP_REP_PROMINENCE, PUSHUP_TOP_BODY_WINDOW,
)

REP_PARAMS = dict(
    down_ratio=PUSHUP_ADAPTIVE_DOWN_RATIO, up_ratio=PUSHUP_ADAPTIVE_UP_RATIO,
    min_span=PUSHUP_ADAPTIVE_MIN_SPAN, window=PUSHUP_ANGLE_SMOOTH_WINDOW,
    fixed_down=PUSHUP_ELBOW_DOWN_ANGLE, fixed_up=PUSHUP_ELBOW_UP_ANGLE,
    prominence=PUSHUP_REP_PROMINENCE,
)


def up_threshold(smooth):
    """count_reps와 같은 공식으로 이 영상의 UP 임계를 계산한다."""
    if len(smooth) >= 20:
        q = statistics.quantiles(smooth, n=100)
        low, high = q[4], q[94]
        span = high - low
        if span >= PUSHUP_ADAPTIVE_MIN_SPAN:
            return low + PUSHUP_ADAPTIVE_UP_RATIO * span
    return PUSHUP_ELBOW_UP_ANGLE


def extract(item):
    """캐시 한 편 → (reps, top 스트림, 캘리브레이션 부호 표본, up 임계).

    top 스트림: [(frame, dev, below)] — 평활각 > UP 임계 & 이탈각 측정된 프레임.
    캘리브레이션: 첫 dip(평활각 ≤ UP 임계 최초 도달) 이전 top 프레임의 부호 표본.
    """
    rows = [r for r in item["rows"] if r[1] is not None]
    angles = [(r[0], r[1]) for r in rows]
    n, reps = count_reps(angles, item["fps"], **REP_PARAMS)
    smooth = median_smooth([a for _, a in angles], PUSHUP_ANGLE_SMOOTH_WINDOW)
    up_t = up_threshold(smooth)

    top = []          # (frame, dev, below|None)
    calib = []        # 부호 표본 (첫 dip 이전)
    first_dip = None  # 평활각이 처음 UP 임계 아래로 내려간 프레임
    for (f, _), s, row in zip(angles, smooth, rows):
        if s > up_t:
            if row[2] is not None:
                top.append((f, row[2], row[3]))
                if first_dip is None and row[3] is not None:
                    calib.append(row[2] if row[3] else -row[2])
        elif first_dip is None:
            first_dip = f
    return {"n": n, "reps": reps, "top": top, "calib": calib,
            "up_t": up_t, "first_dip": first_dip}


def rep_signed_median(top, bottom_frame, window=PUSHUP_TOP_BODY_WINDOW,
                      min_samples=3):
    """rep 최저점 직전 top 윈도의 부호 중앙값(프로덕션 _top_body_line_delta의 rep측)."""
    before = [t for t in top if t[0] < bottom_frame]
    win = before[-window:]
    signed = [d if b else -d for _, d, b in win if b is not None]
    if len(signed) < min_samples:
        return None
    return statistics.median(signed)


# --- 기준선 전략 ---------------------------------------------------------

def baseline_all(calib, min_samples=9):
    """현행: 캘리브레이션 구간 전체의 중앙값."""
    if len(calib) < min_samples:
        return None
    return statistics.median(calib)


def baseline_tail(calib, k, min_samples=9):
    """꼬리 k개(첫 dip 직전 = 실제 플랭크 자세)만 쓴다 — 준비 동작 오염 차단."""
    if len(calib) < min_samples:
        return None
    return statistics.median(calib[-k:])


def baseline_stable_tail(calib, k=15, max_sd=4.0, min_samples=9):
    """꼬리 k개가 안정(sd ≤ max_sd)할 때만 기준선으로 인정한다."""
    if len(calib) < min_samples:
        return None
    tail = calib[-k:]
    if len(tail) >= 2 and statistics.stdev(tail) > max_sd:
        return None
    return statistics.median(tail)


STRATEGIES = {
    "all(구현행)": baseline_all,
    "tail9": lambda c: baseline_tail(c, 9),
    "tail15": lambda c: baseline_tail(c, 15),
    "tail30": lambda c: baseline_tail(c, 30),
    "stable15sd4": baseline_stable_tail,
    "stable15sd6": lambda c: baseline_stable_tail(c, 15, 6.0),
}


def deltas_for(item, strategy):
    """한 편의 rep별 델타 목록(None=판정 보류)과 기준선."""
    ex = extract(item)
    base = strategy(ex["calib"])
    out = []
    for rep in ex["reps"]:
        med = rep_signed_median(ex["top"], rep["bottom"])
        if base is None or med is None:
            out.append(None)
        else:
            out.append(med - base)
    return base, out, ex


def diag(cache_dir: Path):
    """클립별 진단: 캘리브레이션 분포·rep별 부호 중앙값·현행 델타."""
    for path in sorted(cache_dir.glob("local_*.json")):
        item = json.loads(path.read_text(encoding="utf-8"))
        ex = extract(item)
        calib = ex["calib"]
        line = f"{item['id']:<16} rep {ex['n']}  calib {len(calib)}표본"
        if calib:
            q = (min(calib), statistics.median(calib), max(calib))
            line += f" [{q[0]:6.1f} ~ 중앙 {q[1]:6.1f} ~ {q[2]:6.1f}]"
            tail = calib[-15:]
            line += f" 꼬리15 중앙 {statistics.median(tail):6.1f}"
            if len(tail) >= 2:
                line += f" sd {statistics.stdev(tail):4.1f}"
        print(line)
        base = baseline_all(calib)
        meds = [rep_signed_median(ex["top"], r["bottom"]) for r in ex["reps"]]
        meds_s = ["  없음" if m is None else f"{m:6.1f}" for m in meds]
        print(f"  rep 부호 중앙값: {' '.join(meds_s)}")
        if base is not None:
            ds = ["  없음" if m is None else f"{m - base:6.1f}" for m in meds]
            print(f"  현행 델타     : {' '.join(ds)}  (기준선 {base:.1f})")


def grid(cache_dir: Path):
    """전략 × δ 격자 — 로컬 54 rep(몸통 정상)의 오탐 수와 판정 커버리지."""
    items = [json.loads(p.read_text(encoding="utf-8"))
             for p in sorted(cache_dir.glob("local_*.json"))]
    print(f"로컬 {len(items)}편 (라벨상 몸통 결함 0 → 모든 발화가 오탐)")
    print(f"{'전략':<12} {'기준선있는편':<7} {'판정rep':<7} "
          + "".join(f"δ>{d:<5}" for d in (8, 10, 12, 15, 20, 25)))
    for name, strategy in STRATEGIES.items():
        n_base = 0
        judged = []
        for item in items:
            base, deltas, _ = deltas_for(item, strategy)
            if base is not None:
                n_base += 1
            judged.extend(d for d in deltas if d is not None)
        row = f"{name:<12} {n_base:<7} {len(judged):<7}"
        for d in (8, 10, 12, 15, 20, 25):
            fp = sum(1 for x in judged if abs(x) > d)
            row += f"{fp:<7}"
        print(row)
    if judged:
        mags = sorted(abs(x) for x in judged)
        print(f"\n(마지막 전략의 |델타| 분포: 중앙 {statistics.median(mags):.1f}, "
              f"P90 {mags[int(len(mags)*0.9)]:.1f}, 최대 {mags[-1]:.1f})")


def pushai(cache_dir: Path, warn=15.0, severe=25.0):
    """PushAI 100클립에 채택 운영점(stable tail15 sd≤6 + δ15/25)을 적용한다.

    주의: 클립당 rep이 대부분 1개라 rep top 윈도 ≈ 캘리브레이션 꼬리 → 델타가
    구조적으로 0 근처다. 여기서 보는 것은 (1) 와일드 클립의 기준선 확보율,
    (2) correct 그룹 오탐 없음, (3) 결함 클립의 발화 여부(있으면 보너스)다.
    """
    prod = lambda c: baseline_stable_tail(c, 15, 6.0)  # noqa: E731
    stats = {}
    flagged = []
    for path in sorted(cache_dir.glob("pushai_*.json")):
        item = json.loads(path.read_text(encoding="utf-8"))
        group = item["group"]
        s = stats.setdefault(group, {"clips": 0, "with_reps": 0, "with_base": 0,
                                     "judged": 0, "warn": 0, "severe": 0})
        s["clips"] += 1
        base, deltas, ex = deltas_for(item, prod)
        if ex["n"]:
            s["with_reps"] += 1
        if base is not None:
            s["with_base"] += 1
        for i, d in enumerate(deltas):
            if d is None:
                continue
            s["judged"] += 1
            if abs(d) > severe:
                s["severe"] += 1
                flagged.append((item["id"], group, i + 1, round(d, 1), "ERROR"))
            elif abs(d) > warn:
                s["warn"] += 1
                flagged.append((item["id"], group, i + 1, round(d, 1), "WARN"))
    for group, s in sorted(stats.items()):
        print(f"[{group}] 클립 {s['clips']} / rep 있음 {s['with_reps']} / "
              f"기준선 확보 {s['with_base']} / 판정 rep {s['judged']} / "
              f"WARN {s['warn']} / ERROR {s['severe']}")
    if flagged:
        print("\n발화 목록:")
        for vid, group, rep, d, tier in flagged:
            print(f"  {group}/{vid} rep{rep}: 델타 {d:+.1f}° {tier}")


if __name__ == "__main__":
    cache = Path(sys.argv[1])
    mode = sys.argv[2] if len(sys.argv) > 2 else "diag"
    if mode == "diag":
        diag(cache)
    elif mode == "pushai":
        pushai(cache)
    else:
        grid(cache)

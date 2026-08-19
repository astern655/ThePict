"""rep 카운트 로직 오프라인 실험대.

프로덕션 경로(MedianSmoother → 적응 임계 → 히스테리시스 상태기계 →
유실 구간 폐기)를 각도 시계열만으로 재현한다. 캐시가 있으면 YOLO 없이
파라미터를 격자 탐색할 수 있다.
"""
import json
import statistics
from pathlib import Path


def median_smooth(values, window):
    """ai.analysis.filters.MedianSmoother와 같은 동작(뒤쪽 윈도 중앙값)."""
    if window <= 1:
        return list(values)
    out, buf = [], []
    for v in values:
        buf.append(v)
        if len(buf) > window:
            buf.pop(0)
        out.append(statistics.median(buf))
    return out


def local_peak_median(values, up_hint):
    """rep 사이 '팔 편 봉우리'의 중앙값. 못 구하면 None.

    p95는 운동 외 구간(준비·마무리)에 오염돼 UP 경계를 띄우는 문제가 있다
    (docs/PUSHUP_TUNING.md §7-A-1). 봉우리 중앙값은 소수의 극단 프레임에 둔감하다.
    up_hint 위로 올라갔다 내려오는 구간마다 최댓값을 하나씩 모은다.
    """
    peaks, cur = [], None
    for v in values:
        if v >= up_hint:
            cur = v if cur is None else max(cur, v)
        elif cur is not None:
            peaks.append(cur)
            cur = None
    if cur is not None:
        peaks.append(cur)
    return statistics.median(peaks) if peaks else None


def count_reps(angles, fps, *, down_ratio=0.35, up_ratio=0.70, min_span=25.0,
               window=7, gap_sec=0.5, fixed_down=130.0, fixed_up=160.0,
               partial_mid=True, min_rep_frames=0, prominence=0.0,
               hi_pct=94, peak_ref=False):
    """(rep 수, rep 구간 목록). angles는 [(frame, angle)] 원시값.

    prominence > 0이면 'DOWN 진입 후 최저점이 진입 임계보다 이만큼 더
    내려가야 rep으로 인정'하는 추가 조건을 건다(잔떨림 방어).
    min_rep_frames > 0이면 그보다 짧은 rep을 버린다(고주파 오검출 방어).
    hi_pct는 상단 기준 백분위 인덱스(94 = p95).
    peak_ref=True면 상단 기준을 백분위 대신 국소 봉우리 중앙값으로 바꾼다.
    """
    if not angles:
        return 0, []
    frames = [f for f, _ in angles]
    raw = [a for _, a in angles]
    smooth = median_smooth(raw, window)

    down_t, up_t = fixed_down, fixed_up
    if len(smooth) >= 20:
        q = statistics.quantiles(smooth, n=100)
        low, high = q[4], q[hi_pct]
        if peak_ref:
            # 1차 추정으로 봉우리를 모은 뒤 그 중앙값을 상단 기준으로 삼는다.
            hint = low + 0.60 * (high - low)
            peak = local_peak_median(smooth, hint)
            if peak is not None:
                high = peak
        span = high - low
        if span >= min_span:
            down_t = low + down_ratio * span
            up_t = low + up_ratio * span
    partial_t = (down_t + up_t) / 2 if partial_mid else down_t

    max_gap = max(1, round(fps * gap_sec)) if fps else 15
    state = "UP"
    reps = []
    dip_start = None
    rep_min = 180.0
    bottom_frame = 0
    last_frame = None
    await_up = False

    for f, a in zip(frames, smooth):
        if last_frame is not None and f - last_frame > max_gap:
            state, await_up = "UP", True
            dip_start, rep_min = None, 180.0
        last_frame = f
        if await_up:
            if a <= up_t:
                continue
            await_up = False
        if a < up_t:
            if dip_start is None:
                dip_start = f
            if a < rep_min:
                rep_min, bottom_frame = a, f
        if state == "UP":
            if a < down_t:
                state = "DOWN"
            elif a > up_t and dip_start is not None:
                dip_start, rep_min = None, 180.0
        elif state == "DOWN" and a > up_t:
            state = "UP"
            start = dip_start if dip_start is not None else f
            deep_enough = rep_min <= down_t - prominence
            long_enough = (f - start) >= min_rep_frames
            if deep_enough and long_enough:
                reps.append({"start": start, "bottom": bottom_frame, "end": f,
                             "min_angle": round(rep_min, 1)})
            dip_start, rep_min = None, 180.0
    return len(reps), reps


def match(reps, segments):
    """전문가 세그먼트에 엔진 rep을 겹침 최대로 짝짓는다."""
    used, matched = set(), 0
    for seg in sorted(segments, key=lambda s: s["start"]):
        best, best_ov = None, 0
        for i, r in enumerate(reps):
            if i in used:
                continue
            ov = min(seg["end"], r["end"]) - max(seg["start"], r["start"])
            if ov > best_ov:
                best, best_ov = i, ov
        if best is not None:
            used.add(best)
            matched += 1
    return matched


def evaluate(cache, **params):
    """전체 성적: 카운트 오차, 정확 일치 영상 수, 세그먼트 매칭률."""
    rows = []
    for item in cache["rehab"]:
        n, reps = count_reps(item["angles"], item["fps"], **params)
        truth = len(item["segments"])
        rows.append({
            "set": "rehab", "id": item["id"], "engine": n, "truth": truth,
            "matched": match(reps, item["segments"]),
        })
    for item in cache["local"]:
        n, _ = count_reps(item["angles"], item["fps"], **params)
        rows.append({
            "set": "local", "id": item["id"], "engine": n,
            "truth": item["expected_reps"], "matched": None,
        })
    exact = sum(r["engine"] == r["truth"] for r in rows)
    abs_err = sum(abs(r["engine"] - r["truth"]) for r in rows)
    total_truth = sum(r["truth"] for r in rows)
    rehab = [r for r in rows if r["set"] == "rehab"]
    matched = sum(r["matched"] for r in rehab)
    rehab_truth = sum(r["truth"] for r in rehab)
    return {
        "videos": len(rows), "exact": exact,
        "exact_rate": exact / len(rows),
        "abs_err": abs_err, "total_truth": total_truth,
        "count_accuracy": max(0.0, 1 - abs_err / total_truth),
        "seg_match_rate": matched / rehab_truth if rehab_truth else 0.0,
        "rows": rows,
    }


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))

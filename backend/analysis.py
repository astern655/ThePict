"""세션의 관절 판정(checks)을 한국어 문장으로 바꾸는 규칙 기반 분석.

LLM 없음. pose_eval.RULES의 임계값과 세트별 checks만 재료로 쓴다.
점수 숫자만으로는 자세가 안 고쳐지므로, 모든 문장은 "무엇을 / 얼마나 / 어떻게"를 담는다.
"""

import pose_eval

# name -> 표시 라벨, 범위를 읽을 RULES 키, 이탈 방향별 진단·교정 문장
CHECK_META = {
    "knee_angle": {
        "label": "무릎 각도",
        "range": ("knee_angle_min", "knee_angle_max"),
        "high": "무릎을 충분히 굽히지 못했어요(너무 얕게 앉음)",
        "low": "무릎이 필요 이상으로 접혔어요(너무 깊게 앉음)",
        "fix_high": "엉덩이를 뒤로 더 빼면서 허벅지가 바닥과 평행해질 때까지 내려가세요. 옆에서 봤을 때 무릎이 직각보다 더 접히는지 확인하면 됩니다.",
        "fix_low": "바닥까지 주저앉지 말고 허벅지가 바닥과 평행해지는 지점에서 멈췄다가 발뒤꿈치로 밀어 올라오세요.",
    },
    "hip_angle": {
        "label": "고관절 각도",
        "range": ("hip_angle_min", "hip_angle_max"),
        "high": "고관절이 덜 접혔어요(엉덩이를 뒤로 덜 뺌)",
        "low": "고관절이 과하게 접혔어요(상체가 허벅지에 붙을 만큼 접힘)",
        "fix_high": "앉기 시작할 때 무릎부터 굽히지 말고 엉덩이를 의자에 앉듯 뒤로 먼저 보내세요.",
        "fix_low": "엉덩이를 뒤로 빼는 폭을 줄이고, 가슴을 편 채 상체를 조금 더 세워서 내려가세요.",
    },
    "back_angle": {
        "label": "허리 각도",
        "range": (None, "back_angle_max"),
        "high": "상체를 과도하게 숙였어요",
        "low": "",
        "fix_high": "시선을 정면에 두고 가슴을 편 채로 내려가세요. 내려가는 동안 배에 힘을 주고 갈비뼈가 앞으로 무너지지 않게 유지하면 상체가 덜 숙여집니다.",
        "fix_low": "",
    },
    # --- 영상 분석(AI 엔진, video_analysis.py)이 올리는 항목 ---
    # 위 세 항목이 "한 프레임의 각도"인 것과 달리, 아래 둘은 rep 최저점(가장 깊이 앉은
    # 순간)들을 평균한 값이다. 판정 근거는 docs/CAPTURE_AND_SQUAT_CRITERIA.md.
    "squat_depth": {
        "label": "앉은 깊이",
        "range": (None, "squat_depth_max"),
        "high": "충분히 앉지 못했어요(무릎이 덜 굽음)",
        "low": "",
        "fix_high": "허벅지가 바닥과 평행해질 때까지 내려가세요. 엉덩이를 뒤로 빼면서 무릎을 굽히면 상체를 세운 채로 더 깊이 앉을 수 있습니다.",
        "fix_low": "",
    },
    "torso_shin_diff": {
        # 라벨 뒤에 "가/는/부터" 조사가 그대로 붙는다. 받침으로 끝나면("앞숙임가")
        # 문장이 어색해지므로 모음으로 끝나는 표현을 쓴다.
        "label": "상체 앞숙임 정도",
        "range": (None, "torso_shin_diff_max"),
        "high": "정강이 기울기에 비해 상체가 과하게 접혔어요",
        "low": "",
        "fix_high": "엉덩이만 뒤로 빼지 말고 무릎을 먼저 굽혀 앉으세요. 내려가는 동안 가슴을 세우고 시선을 정면에 두면 상체가 정강이를 따라 자연스럽게 기웁니다.",
        "fix_low": "",
    },
}


def _range(exercise_id: str, check_name: str) -> tuple:
    """(low, high). 규칙이 없는 항목은 (None, None)."""
    meta = CHECK_META.get(check_name)
    rules = pose_eval.RULES.get(exercise_id)
    if meta is None or rules is None:
        return (None, None)
    lo_key, hi_key = meta["range"]
    return (rules.get(lo_key) if lo_key else 0, rules.get(hi_key) if hi_key else None)


def _fmt_range(lo, hi) -> str:
    if lo in (None, 0) and hi is not None:
        return f"{hi}° 이하"
    if lo is not None and hi is not None:
        return f"{lo}~{hi}°"
    return "목표 범위"


def has_score(session: dict) -> bool:
    """자세를 실제로 측정한 세트가 하나라도 있는가.

    없으면 avg_form_score는 0인데, 그건 "0점"이 아니라 "점수 없음"이다.
    이걸 구분하지 않으면 "지난 세션과 같은 0점이에요" 같은 헛소리가 나간다.
    """
    return any(s.get("form_score") is not None for s in session.get("sets") or [])


def aggregate(sets: list[dict]) -> dict:
    """세트별 checks를 항목별로 집계. checks가 없는 세트는 그냥 빠진다."""
    agg = {}
    for s in sets:
        for c in s.get("checks") or []:
            a = agg.setdefault(c["name"], {"total": 0, "bad": 0, "values": []})
            a["total"] += 1
            if c.get("status") == "bad":
                a["bad"] += 1
            a["values"].append(c["value"])
    for a in agg.values():
        a["mean"] = round(sum(a["values"]) / len(a["values"]), 1)
    return agg


def _deviation(mean: float, lo, hi) -> float:
    """목표 범위 밖으로 벗어난 크기(도). 범위 안이면 0."""
    if hi is not None and mean > hi:
        return mean - hi
    if lo is not None and mean < lo:
        return lo - mean
    return 0.0


def _direction(mean: float, lo, hi) -> str:
    if hi is not None and mean > hi:
        return "high"
    if lo is not None and mean < lo:
        return "low"
    return ""


def build(session: dict, previous: dict | None, exercise_name: str | None = None) -> dict:
    """세션 하나에 대한 문장 분석. 재료가 없으면 없다고 정직하게 말한다."""
    exercise_id = session["exercise_id"]
    exercise_name = exercise_name or exercise_id
    sets = session.get("sets") or []
    agg = aggregate(sets)

    result = {
        "session_id": session["id"],
        "exercise_id": exercise_id,
        "date": session["date"],
        "avg_form_score": session["avg_form_score"] if has_score(session) else None,
        "has_joint_data": bool(agg),
        # False면 avg_form_score는 None이다. 점수 자리에 0을 그리면 안 된다.
        "has_score": has_score(session),
        "compared_with": None,
        "good": [],
        "bad": [],
        "change": [],
        "next": [],
        "notes": [],
    }

    if not agg:
        result["notes"].append(
            "이 세션에는 관절 판정 데이터가 없어서 자세를 문장으로 분석할 수 없어요. "
            "다음 운동부터는 카메라를 켜고 측정하면 어느 관절이 문제였는지 알려드릴 수 있습니다."
        )
    else:
        result["good"], result["bad"] = _good_bad(exercise_id, agg)
        result["next"] = _next_actions(exercise_id, agg)

    result["change"], change_notes = _change(session, previous, exercise_id, exercise_name, agg)
    result["notes"].extend(change_notes)
    if previous is not None:
        result["compared_with"] = {"session_id": previous["id"], "date": previous["date"]}
    return result


def _good_bad(exercise_id: str, agg: dict) -> tuple[list, list]:
    good, bad = [], []
    for name, a in agg.items():
        meta = CHECK_META.get(name)
        if meta is None:
            continue
        lo, hi = _range(exercise_id, name)
        rng = _fmt_range(lo, hi)
        if a["bad"] == 0:
            good.append(
                f"{meta['label']}는 {a['total']}세트 전부 목표 범위({rng}) 안이었어요. 평균 {a['mean']}°."
            )
        else:
            direction = _direction(a["mean"], lo, hi)
            diag = meta.get(direction) or "목표 범위를 벗어났어요"
            bad.append(
                f"{a['total']}세트 중 {a['bad']}세트에서 {meta['label']}가 목표 범위({rng})를 벗어났어요. "
                f"평균 {a['mean']}° — {diag}."
            )
    return good, bad


def _next_actions(exercise_id: str, agg: dict) -> list:
    """가장 문제가 컸던 1~2개 항목만 콕 집어 교정 지시. 나머지는 소음이다."""
    ranked = []
    for name, a in agg.items():
        if a["bad"] == 0 or name not in CHECK_META:
            continue
        lo, hi = _range(exercise_id, name)
        ranked.append((a["bad"] / a["total"], _deviation(a["mean"], lo, hi), name))
    ranked.sort(reverse=True)

    out = []
    for bad_rate, dev, name in ranked[:2]:
        meta = CHECK_META[name]
        lo, hi = _range(exercise_id, name)
        fix = meta.get(f"fix_{_direction(agg[name]['mean'], lo, hi)}") or meta["fix_high"]
        out.append(
            f"{meta['label']}부터 잡으세요(세트의 {round(bad_rate * 100)}%에서 이탈, 목표에서 평균 {round(dev, 1)}° 벗어남). {fix}"
        )
    return out


def _change(
    session: dict, previous: dict | None, exercise_id: str, exercise_name: str, agg: dict
) -> tuple[list, list]:
    if previous is None:
        return [], [f"비교할 이전 {exercise_name} 세션이 없어요. 이번이 첫 기록입니다."]

    # 한쪽이라도 자세를 안 쟀으면 점수 비교 자체가 성립하지 않는다.
    # (avg_form_score 0은 "0점"이 아니라 "점수 없음"이다)
    comparable = has_score(session) and has_score(previous)
    score_delta = (
        round(session["avg_form_score"] - previous["avg_form_score"], 1) if comparable else 0
    )
    prev_agg = aggregate(previous.get("sets") or [])

    if not agg or not prev_agg:
        note = f"이전 세션({previous['date']})에 관절 판정 데이터가 없어 원인까지는 비교할 수 없어요."
        if comparable:
            note += (
                f" 평균 점수는 {previous['avg_form_score']}점 → "
                f"{session['avg_form_score']}점입니다."
            )
        else:
            note += " 자세를 측정한 기록이 없어 점수도 비교할 수 없습니다."
        return [], [note]

    # 항목별로 "목표에서 얼마나 벗어났나"의 변화를 계산 — 개선분이 큰 순으로 정렬
    moves = []
    for name in set(agg) & set(prev_agg):
        if name not in CHECK_META:
            continue
        lo, hi = _range(exercise_id, name)
        before, now = prev_agg[name]["mean"], agg[name]["mean"]
        improvement = _deviation(before, lo, hi) - _deviation(now, lo, hi)
        moves.append((abs(improvement), improvement, name, before, now))
    moves.sort(reverse=True)

    lines = []
    for i, (_, improvement, name, before, now) in enumerate(moves[:2]):
        label = CHECK_META[name]["label"]
        if abs(before - now) < 1:
            lines.append(f"{label}는 {before}° → {now}°로 거의 그대로예요.")
            continue
        if improvement > 0:
            lines.append(f"{label}가 지난 세션 {before}°에서 이번에 {now}°로 목표에 가까워졌어요.")
        elif improvement < 0:
            lines.append(f"{label}가 지난 세션 {before}°에서 이번에 {now}°로 목표에서 더 멀어졌어요.")
        else:
            lines.append(f"{label}는 {before}° → {now}°로 바뀌었지만 둘 다 목표 범위 안이에요.")

        if i == 0 and score_delta != 0 and improvement != 0:
            cause = "상승" if score_delta > 0 else "하락"
            sign = f"+{score_delta}" if score_delta > 0 else str(score_delta)
            lines.append(f"점수 {cause}({sign}점)의 주 원인은 {label} 변화입니다.")

    if comparable and score_delta == 0 and not any("주 원인" in ln for ln in lines):
        lines.append(f"평균 점수는 {session['avg_form_score']}점으로 지난 세션과 같아요.")
    return lines, []


def day_summary(sessions: list[dict]) -> list:
    """캘린더에서 날짜를 탭했을 때 맨 위에 보여줄 한 줄짜리 요약."""
    if not sessions:
        return ["이 날에는 기록된 운동이 없어요."]
    total_reps = sum(s["total_reps"] for s in sessions)
    head = f"{len(sessions)}개 세션, 총 {total_reps}회를 했어요."
    # 자세를 잰 세션만 평균에 넣는다. 하나도 없으면 점수를 지어내지 않고 그렇다고 말한다.
    scored = [s for s in sessions if has_score(s)]
    if not scored:
        return [f"{head} 자세를 측정한 기록이 없어 점수는 없습니다."]
    avg = round(sum(s["avg_form_score"] for s in scored) / len(scored), 1)
    return [f"{head} 평균 자세 점수는 {avg}점입니다."]

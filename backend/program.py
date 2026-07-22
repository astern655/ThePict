"""운동 프로그램: 난이도별 기본 프리셋 · 점진 증가 · 개인 설정 해석.

순수 함수만 둔다(DB 접근 없음). main.py가 값을 읽어 넣고 결과를 그대로 반환한다.
"""

LEVELS = ("beginner", "intermediate", "advanced")
DEFAULT_LEVEL = "beginner"
LEVEL_LABEL = {"beginner": "초급", "intermediate": "중급", "advanced": "상급"}

# 근거(ACSM/NSCA 저항운동 가이드라인 통용값):
# - 초보자는 1~3세트 8~12회. 세트 수를 적게 두는 대신 세트 간 휴식을 길게 줘야
#   피로 누적으로 자세가 무너지는 것을 막을 수 있다. 이 앱은 자세교정이 목적이라
#   "많이"보다 "제대로"가 우선이므로 초급 휴식을 가장 길게 잡았다.
# - 숙련될수록 세트 수를 늘리고 휴식을 줄여 대사 스트레스를 높인다.
# 맨몸 운동(스쿼트/런지/푸시업): 부하가 낮아 반복수를 높게, 휴식을 짧게 가져간다.
_BODYWEIGHT = {
    "beginner": {"sets": 2, "reps": 10, "rest_sec": 90},
    "intermediate": {"sets": 3, "reps": 12, "rest_sec": 60},
    "advanced": {"sets": 4, "reps": 15, "rest_sec": 45},
}
# 중량 복합관절(데드리프트/벤치프레스): 신경계 피로가 커서 NSCA 권장대로
# 세트 간 2~5분을 줘야 다음 세트에서 자세가 유지된다. 상급은 저반복 고강도.
_WEIGHTED = {
    "beginner": {"sets": 2, "reps": 8, "rest_sec": 120},
    "intermediate": {"sets": 3, "reps": 8, "rest_sec": 120},
    "advanced": {"sets": 4, "reps": 6, "rest_sec": 180},
}
PRESETS = {
    "squat": _BODYWEIGHT,
    "lunge": _BODYWEIGHT,
    "pushup": _BODYWEIGHT,
    "deadlift": _WEIGHTED,
    "bench_press": _WEIGHTED,
}

# 점진 증가 근거: 주 3회 운동을 가정하면 3세션 ≈ 1주.
# 1주마다 한 단계씩 올리는 것이 ACSM의 점진적 과부하(주당 2~10% 증량) 취지에 맞다.
# 세트를 먼저 2세트까지 올리고(총 운동량 확보), 그 다음부터 반복수를 올린다.
# 가이드라인이므로 상한을 둔다 — 무한정 늘어나면 가이드가 아니라 사고다.
SESSIONS_PER_STEP = 3
MAX_STEP = 4  # 12세션(약 4주) 이후로는 자동 증가 없음 → 그 다음은 난이도를 올리거나 개인 설정으로
MAX_EXTRA_SETS = 2
REPS_PER_STEP = 2


def presets_for(exercise_id: str) -> dict:
    return PRESETS.get(exercise_id, _BODYWEIGHT)


def progression_step(completed_sessions: int) -> int:
    return min(completed_sessions // SESSIONS_PER_STEP, MAX_STEP)


def resolve(exercise_id: str, level: str, completed_sessions: int, override: dict | None) -> dict:
    """오늘의 계획. 우선순위: 개인 설정 > 점진 증가 > 기본 프리셋 (필드 단위)."""
    override = override or {}
    level = override.get("level") or level or DEFAULT_LEVEL
    base = presets_for(exercise_id)[level]

    step = progression_step(completed_sessions)
    extra_sets = min(step, MAX_EXTRA_SETS)
    extra_reps = REPS_PER_STEP * max(0, step - MAX_EXTRA_SETS)
    progressed = {
        "sets": base["sets"] + extra_sets,
        "reps": base["reps"] + extra_reps,
        "rest_sec": base["rest_sec"],  # 휴식은 자동으로 줄이지 않는다 — 피로 관리는 사용자 몫
    }

    overridden = [f for f in ("sets", "reps", "rest_sec") if override.get(f) is not None]
    final = {f: (override[f] if f in overridden else progressed[f]) for f in progressed}

    if overridden:
        source = "custom"
    elif step > 0:
        source = "progression"
    else:
        source = "preset"

    return {
        "exercise_id": exercise_id,
        "level": level,
        **final,
        "source": source,
        "overridden_fields": overridden,
        "preset": base,
        "completed_sessions": completed_sessions,
        "progression_step": step,
        "next_step_in_sessions": (
            None if step >= MAX_STEP else SESSIONS_PER_STEP - (completed_sessions % SESSIONS_PER_STEP)
        ),
        "message": _message(exercise_id, level, base, final, step, overridden, completed_sessions),
    }


def _message(exercise_id, level, base, final, step, overridden, completed) -> str:
    lv = LEVEL_LABEL[level]
    head = f"{lv} 기준 {final['sets']}세트 × {final['reps']}회, 세트 사이 {final['rest_sec']}초 휴식이에요."

    if overridden:
        names = {"sets": "세트 수", "reps": "횟수", "rest_sec": "휴식 시간"}
        which = ", ".join(names[f] for f in overridden)
        return f"{head} 직접 설정한 {which}을(를) 우선 적용했습니다."

    if step == 0:
        if completed == 0:
            return f"{head} 첫 기록이라 {lv} 기본값 그대로 시작합니다."
        left = SESSIONS_PER_STEP - (completed % SESSIONS_PER_STEP)
        return f"{head} {left}세션 더 하면 세트를 한 단계 올립니다."

    week = step + 1
    changed = []
    if final["sets"] > base["sets"]:
        changed.append(f"세트가 {base['sets']} → {final['sets']}세트")
    if final["reps"] > base["reps"]:
        changed.append(f"세트당 횟수가 {base['reps']} → {final['reps']}회")
    grew = ", ".join(changed)
    if step >= MAX_STEP:
        return f"{head} {completed}세션을 채워 자동 증가는 여기까지입니다({grew}). 더 올리려면 난이도를 올리거나 직접 설정하세요."
    left = SESSIONS_PER_STEP - (completed % SESSIONS_PER_STEP)
    return f"{head} {completed}세션을 완료해 {week}주차 기준으로 {grew}로 늘었어요. {left}세션 더 하면 한 단계 더 올라갑니다."

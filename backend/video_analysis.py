"""영상 한 편 → 스쿼트 리포트. 로컬 AI 엔진(`ai/`)을 부르는 백엔드 진입점.

프레임 단위 API(`/inference/pose`)는 "지금 이 순간의 관절각"만 본다. 반복 횟수,
rep별 올바름/교정필요/잘못됨 판정, 측면 촬영 검증은 영상 전체를 봐야 나오므로
그 일은 전부 AI 엔진(`ai.engine.analyze_video`)에 맡긴다.

세트 하나 = 영상 한 편으로 본다. `to_set()` 이 리포트를 기존 `/sessions` 스키마
(reps / form_score / checks)로 낮춰 주므로, 저장·분석(`analysis.py`) 경로는
그대로 재사용된다.
"""

import ai_bridge

SUPPORTED_EXERCISES = {"squat"}


class UnsupportedExercise(ValueError):
    """AI 엔진이 아직 분석하지 못하는 운동. 호출부가 400으로 바꾼다."""


# rep 판정 → 100점 만점 점수. 세트 점수는 rep 점수의 평균이다.
# (기존 pose_eval의 form_score와 같은 0~100 척도라 앱/분석 코드가 그대로 쓴다)
VERDICT_SCORE = {"correct": 100.0, "needs_work": 70.0, "incorrect": 30.0}

# AI 엔진의 결함 코드 → `checks` 항목 이름.
# 깊이는 rep마다 항상 판정되고(good_depth 포함), 상체는 결함일 때만 측정값이 남는다.
DEPTH_CODES = {"good_depth", "shallow_depth", "very_shallow_depth"}
TORSO_CODES = {"torso_lean", "excessive_torso_lean"}

DEPTH_CHECK = "squat_depth"
TORSO_CHECK = "torso_shin_diff"


def analyze(video_path: str, exercise_id: str, *, save_annotated: bool = False) -> dict:
    """영상을 분석해 `Report.to_dict()` 를 반환한다.

    save_annotated=True면 관절을 그린 결과 영상을 data/output/에 남기고 경로를
    리포트에 담는다. 서버 기본값은 False — 요청마다 영상 파일을 쌓지 않기 위함.
    """
    if exercise_id not in SUPPORTED_EXERCISES:
        raise UnsupportedExercise(exercise_id)
    engine = ai_bridge.load_engine()  # ImportError는 EngineUnavailable로 올라온다
    report = engine.analyze_video(
        video_path, exercise=exercise_id, save_annotated=save_annotated
    )
    return report.to_dict()


def _rep_issues(report: dict, rep_index: int) -> list[dict]:
    return [i for i in report["issues"] if i["rep_index"] == rep_index]


def _mean(values: list[float]) -> float:
    return round(sum(values) / len(values), 1)


def to_set(report: dict) -> dict:
    """리포트를 `/sessions` 의 세트 하나로 낮춘다.

    checks는 rep들의 측정값을 항목별로 평균 낸 것이다. 상체 항목은 엔진이 실제로
    잰 rep이 하나도 없으면(= 모든 rep이 정상) 빼는데, 재지도 않은 값을 "정상"으로
    지어내지 않기 위해서다.
    """
    rep_count = report["rep_count"]
    verdicts = report["rep_verdicts"]
    form_score = (
        round(sum(VERDICT_SCORE[v["verdict"]] for v in verdicts) / len(verdicts), 1)
        if verdicts
        else 0.0
    )

    depth_values: list[float] = []
    depth_bad = 0
    torso_values: list[float] = []

    for rep in range(1, rep_count + 1):
        for issue in _rep_issues(report, rep):
            if issue["measured"] is None:
                continue
            if issue["code"] in DEPTH_CODES:
                depth_values.append(issue["measured"])
                if issue["severity"] != "good":
                    depth_bad += 1
            elif issue["code"] in TORSO_CODES:
                torso_values.append(issue["measured"])

    checks = []
    if depth_values:
        checks.append({
            "name": DEPTH_CHECK,
            "value": _mean(depth_values),
            "status": "bad" if depth_bad else "ok",
            "message": "" if not depth_bad else f"{depth_bad}회차에서 깊이가 모자랐습니다",
        })
    if torso_values:
        # 측정값이 남았다는 것 자체가 기준선을 넘었다는 뜻이다(정상이면 엔진이 침묵).
        checks.append({
            "name": TORSO_CHECK,
            "value": _mean(torso_values),
            "status": "bad",
            "message": f"{len(torso_values)}회차에서 상체가 과하게 앞으로 접혔습니다",
        })

    return {"reps": rep_count, "form_score": form_score, "checks": checks}

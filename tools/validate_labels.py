"""라벨 파일 검사 + 엔진 출력 대조 (측면 촬영 전용).

두 가지 일을 한다.

1. **라벨 파일 자체 검사** — 영상 없이도 돌아간다.
   허용되지 않은 코드, 판정과 코드의 모순, 같은 축의 코드 중복, 구간 시각 오류를 잡는다.
2. **엔진 출력 대조** — 각 영상을 `analyze_video`로 돌려 라벨과 비교하고,
   rep 카운트 정확도·판정 정확도·코드별 precision/recall을 집계한다.

라벨이 정답 기준이다. rep 개수가 어긋나면 구간 시각의 겹침으로 짝을 지어,
검출 못 한 rep(missed)과 없는 rep을 만든 것(spurious)을 따로 센다.

운동별로 결함 코드 표가 다르므로(`EXERCISE_SCHEMA`) `--exercise`로 고른다.
라벨 파일도 운동마다 따로 둔다(`data/<운동>_labels.json`).

실행:
    python -m tools.validate_labels --check-only            # 스쿼트 라벨만 검사
    python -m tools.validate_labels                         # 영상까지 돌려 대조
    python -m tools.validate_labels --exercise pushup       # 푸시업
"""
from __future__ import annotations

import argparse
import json
import sys
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# --- 라벨 스키마 ---------------------------------------------------------
# 코드 → 심각도. 라벨의 판정(label)은 이 표에서 기계적으로 파생되므로,
# 라벨러가 판정을 직접 고민할 필요가 없다(고민하면 오히려 모순이 생긴다).
#
# 운동마다 두 번째 축이 다르다(스쿼트=상체 앞숙임, 푸시업=몸통 일직선). 깊이 축은
# 코드 이름을 공유한다. 다른 운동의 코드를 섞어 적으면 '알 수 없는 코드'로 걸린다.
_DEPTH_SEVERITY = {"shallow_depth": "warning", "very_shallow_depth": "error"}

EXERCISE_SCHEMA: dict[str, dict] = {
    "squat": {
        "code_severity": {
            **_DEPTH_SEVERITY,
            "torso_lean": "warning",
            "excessive_torso_lean": "error",
        },
        # 한 rep에서 같은 축의 코드는 하나만 나올 수 있다(깊이는 3단계 중 하나).
        "axes": {
            "깊이": frozenset(_DEPTH_SEVERITY),
            "상체 앞숙임": frozenset({"torso_lean", "excessive_torso_lean"}),
        },
        "labels_path": "data/squat_labels.json",
    },
    "pushup": {
        "code_severity": {
            **_DEPTH_SEVERITY,
            "body_line_break": "warning",
            "excessive_body_line_break": "error",
        },
        "axes": {
            "깊이": frozenset(_DEPTH_SEVERITY),
            "몸통 일직선": frozenset({"body_line_break", "excessive_body_line_break"}),
        },
        "labels_path": "data/pushup_labels.json",
    },
}
DEFAULT_EXERCISE = "squat"

VIDEO_CODES = {"partial_reps", "low_detection", "not_side_view", "ended_mid_rep",
               "body_line_unverified", "no_reps_detected",
               "tracking_gap", "truncated_video",
               # 푸시업 몸통 캘리브레이션 구간(첫 dip 이전 top)이 없어 몸통 판정을
               # 보류했다는 안내. 영상이 동작 중에 시작하면 나온다.
               "no_body_baseline"}

VALID_LABELS = {"correct", "needs_work", "incorrect"}
REQUIRED_VIEW = "side"  # 두 운동 모두 측면 촬영만 받는다


def _schema(exercise: str) -> dict:
    if exercise not in EXERCISE_SCHEMA:
        raise ValueError(
            f"라벨 스키마가 없는 운동: {exercise!r}. 가능: {', '.join(EXERCISE_SCHEMA)}"
        )
    return EXERCISE_SCHEMA[exercise]


def derive_label(codes: set[str], exercise: str = DEFAULT_EXERCISE) -> str:
    """결함 코드 집합에서 rep 판정을 파생한다(엔진의 verdict_from_issues와 같은 규칙)."""
    severity = _schema(exercise)["code_severity"]
    severities = {severity[c] for c in codes if c in severity}
    if "error" in severities:
        return "incorrect"
    if "warning" in severities:
        return "needs_work"
    return "correct"


# --- 1. 라벨 파일 자체 검사 ----------------------------------------------

def check_label_file(entries: list[dict], exercise: str = DEFAULT_EXERCISE) -> list[str]:
    """라벨 파일의 구조적 오류를 모아 반환한다(빈 리스트면 정상)."""
    schema = _schema(exercise)
    code_severity, axes = schema["code_severity"], schema["axes"]
    problems: list[str] = []
    seen_ids: set[str] = set()

    for entry in entries:
        vid = entry.get("id", "<id 없음>")
        if vid in seen_ids:
            problems.append(f"[{vid}] id가 중복됩니다.")
        seen_ids.add(vid)

        # 라벨 파일에 운동을 적어 뒀다면 검사 중인 운동과 같아야 한다.
        # (스쿼트 라벨을 푸시업으로 채점하면 코드가 전부 '알 수 없는 코드'가 된다)
        declared = entry.get("exercise")
        if declared is not None and declared != exercise:
            problems.append(
                f"[{vid}] exercise가 '{declared}'인데 '{exercise}'로 검사하고 있습니다."
            )

        # view와 not_side_view 기대는 짝으로 일관돼야 한다.
        # 측면(side) 영상이 반려를 기대하거나, 비측면 영상이 반려 없이 통과를
        # 기대하면 라벨이 자기모순이다. (2026-08-17 게이트 강화로 비측면·변형
        # 영상도 '반려를 기대하는 라벨'로 스위트에 남길 수 있게 됐다)
        expects_reject = "not_side_view" in entry.get("expected_video_codes", [])
        if entry.get("view") == REQUIRED_VIEW and expects_reject:
            problems.append(
                f"[{vid}] view가 '{REQUIRED_VIEW}'인데 not_side_view 반려를 "
                f"기대하고 있습니다. 실제로 측면이 아니라면 view를 고치세요."
            )
        if entry.get("view") != REQUIRED_VIEW and not expects_reject:
            problems.append(
                f"[{vid}] view가 '{entry.get('view')}'인데 not_side_view 반려를 "
                f"기대하지 않습니다. 측면이 아니면 반려가 정상 동작입니다."
            )

        bad_video_codes = set(entry.get("expected_video_codes", [])) - VIDEO_CODES
        if bad_video_codes:
            problems.append(f"[{vid}] 알 수 없는 영상 코드: {sorted(bad_video_codes)}")

        reps = entry.get("expected_reps", [])
        if len(reps) != entry.get("expected_rep_count"):
            problems.append(
                f"[{vid}] expected_rep_count({entry.get('expected_rep_count')})와 "
                f"expected_reps 개수({len(reps)})가 다릅니다."
            )

        for position, rep in enumerate(reps, start=1):
            tag = f"[{vid}] {rep.get('rep_index', '?')}회차"

            if rep.get("rep_index") != position:
                problems.append(f"{tag}: rep_index는 1부터 순서대로여야 합니다(기대 {position}).")

            codes = set(rep.get("feedback_codes", []))
            unknown = codes - set(code_severity)
            if unknown:
                problems.append(f"{tag}: 알 수 없는 코드 {sorted(unknown)}")

            for axis_name, axis_codes in axes.items():
                if len(codes & axis_codes) > 1:
                    problems.append(
                        f"{tag}: '{axis_name}' 축의 코드를 두 개 이상 적었습니다 "
                        f"({sorted(codes & axis_codes)}). 축마다 하나만 고르세요."
                    )

            label = rep.get("label")
            if label not in VALID_LABELS:
                problems.append(f"{tag}: label '{label}'은 {sorted(VALID_LABELS)} 중 하나여야 합니다.")
            else:
                expected = derive_label(codes - unknown, exercise)
                if label != expected:
                    problems.append(
                        f"{tag}: 코드 {sorted(codes) or '[]'}면 판정은 '{expected}'인데 "
                        f"'{label}'로 적혀 있습니다."
                    )

            problems.extend(_check_rep_timing(tag, rep))

        problems.extend(_check_rep_overlap(vid, reps))

    return problems


def _check_rep_timing(tag: str, rep: dict) -> list[str]:
    """한 rep의 구간 시각이 start < bottom < end 인지 확인."""
    marks = [rep.get(k) for k in ("start_sec", "bottom_sec", "end_sec")]
    if all(m is None for m in marks):
        return []  # 시각은 선택 항목 — 아예 없으면 넘어간다
    if any(m is None for m in marks):
        return [f"{tag}: 구간 시각은 start/bottom/end를 모두 적거나 모두 비워야 합니다."]
    start, bottom, end = marks
    if not (start < bottom < end):
        return [f"{tag}: 구간 시각 순서가 잘못됐습니다 ({start} < {bottom} < {end} 이어야 함)."]
    return []


def _check_rep_overlap(vid: str, reps: list[dict]) -> list[str]:
    """rep 구간끼리 시간이 겹치지 않는지 확인(겹치면 매칭이 모호해진다)."""
    timed = [r for r in reps if r.get("start_sec") is not None and r.get("end_sec") is not None]
    problems = []
    for earlier, later in zip(timed, timed[1:]):
        if later["start_sec"] < earlier["end_sec"]:
            problems.append(
                f"[{vid}] {earlier['rep_index']}회차와 {later['rep_index']}회차의 "
                f"구간이 겹칩니다({earlier['end_sec']} > {later['start_sec']})."
            )
    return problems


# --- 2. rep 매칭 ---------------------------------------------------------

def _overlap(a_start: float, a_end: float, b_start: float, b_end: float) -> float:
    return max(0.0, min(a_end, b_end) - max(a_start, b_start))


def match_reps(label_reps: list[dict], engine_reps: list) -> list[tuple[dict | None, object | None]]:
    """라벨 rep과 엔진 rep을 짝짓는다.

    라벨에 구간 시각이 있으면 시간 겹침이 가장 큰 것끼리 짝짓고,
    없으면 순번으로 짝짓는다. 짝이 없으면 한쪽이 None인 쌍이 된다
    (라벨만 있음=미검출, 엔진만 있음=오검출).
    """
    has_times = all(r.get("start_sec") is not None for r in label_reps)
    if not has_times:
        pairs: list[tuple[dict | None, object | None]] = []
        for i in range(max(len(label_reps), len(engine_reps))):
            pairs.append((
                label_reps[i] if i < len(label_reps) else None,
                engine_reps[i] if i < len(engine_reps) else None,
            ))
        return pairs

    unused = list(engine_reps)
    pairs = []
    for lab in label_reps:
        best, best_overlap = None, 0.0
        for eng in unused:
            if eng.start_sec is None or eng.end_sec is None:
                continue
            ov = _overlap(lab["start_sec"], lab["end_sec"], eng.start_sec, eng.end_sec)
            if ov > best_overlap:
                best, best_overlap = eng, ov
        if best is not None:
            unused.remove(best)
        pairs.append((lab, best))
    pairs.extend((None, eng) for eng in unused)  # 라벨에 없는 rep을 엔진이 만들어냄
    return pairs


# --- 3. 집계 -------------------------------------------------------------

@dataclass
class Tally:
    """전체 영상에 대한 누적 집계."""
    videos: int = 0
    videos_rep_count_ok: int = 0
    matched_reps: int = 0
    verdict_ok: int = 0
    missed_reps: int = 0      # 라벨에 있는데 엔진이 못 찾음
    spurious_reps: int = 0    # 엔진이 만들었는데 라벨에 없음
    # 코드별 {code: [TP, FP, FN]}
    code_stats: dict[str, list[int]] = field(default_factory=dict)

    def add_code(self, code: str, slot: int) -> None:
        self.code_stats.setdefault(code, [0, 0, 0])[slot] += 1


def compare_video(report, entry: dict, tally: Tally) -> list[str]:
    """한 영상의 엔진 리포트를 라벨과 비교해 사람이 읽을 줄들을 반환."""
    lines = []
    vid = entry["id"]
    tally.videos += 1

    expected_count = entry["expected_rep_count"]
    count_ok = report.rep_count == expected_count
    tally.videos_rep_count_ok += count_ok
    lines.append(_row("rep 수", report.rep_count, expected_count, count_ok))

    expected_partial = entry.get("expected_partial_rep_count", 0)
    lines.append(_row("부분 반복 수", report.partial_rep_count, expected_partial,
                      report.partial_rep_count == expected_partial))

    engine_vcodes = {i.code for i in report.video_issues}
    label_vcodes = set(entry.get("expected_video_codes", []))
    lines.append(_row("영상 코드", sorted(engine_vcodes), sorted(label_vcodes),
                      engine_vcodes == label_vcodes))

    for label_rep, engine_rep in match_reps(entry["expected_reps"], report.reps):
        if engine_rep is None:
            tally.missed_reps += 1
            for code in label_rep["feedback_codes"]:
                tally.add_code(code, 2)  # FN
            lines.append(f"  [{label_rep['rep_index']}회차] 엔진이 이 rep을 검출하지 못함  FAIL")
            continue
        engine_codes = {
            i.code for i in report.issues_for_rep(engine_rep.rep_index)
            if i.severity.value != "good"
        }
        if label_rep is None:
            tally.spurious_reps += 1
            # 없는 rep에 붙은 결함은 전부 오탐이다. 이걸 빼면 정밀도가 부풀려진다.
            for code in engine_codes:
                tally.add_code(code, 1)  # FP
            lines.append(
                f"  [엔진 {engine_rep.rep_index}회차] 라벨에 없는 rep을 검출 "
                f"({engine_rep.start_sec}s~{engine_rep.end_sec}s)  FAIL"
            )
            continue

        tally.matched_reps += 1
        label_codes = set(label_rep["feedback_codes"])
        for code in engine_codes & label_codes:
            tally.add_code(code, 0)  # TP
        for code in engine_codes - label_codes:
            tally.add_code(code, 1)  # FP
        for code in label_codes - engine_codes:
            tally.add_code(code, 2)  # FN

        engine_verdict = report.rep_verdict(engine_rep.rep_index).value
        verdict_ok = engine_verdict == label_rep["label"]
        tally.verdict_ok += verdict_ok
        status = "PASS" if (verdict_ok and engine_codes == label_codes) else "FAIL"
        lines.append(
            f"  [{label_rep['rep_index']}회차] "
            f"코드: 엔진 {sorted(engine_codes) or '[]'} / 라벨 {sorted(label_codes) or '[]'} | "
            f"판정: 엔진 {engine_verdict} / 라벨 {label_rep['label']}  {status}"
        )

    return lines


def _pad(text: str, width: int) -> str:
    """한글은 터미널에서 두 칸을 차지하므로 글자 수가 아닌 표시 폭으로 맞춘다."""
    display_width = sum(2 if unicodedata.east_asian_width(ch) in "WF" else 1 for ch in text)
    return text + " " * max(0, width - display_width)


def _row(name: str, engine, label, ok: bool) -> str:
    return f"  {_pad(name, 16)}: 엔진 {engine} / 라벨 {label}  {'PASS' if ok else 'FAIL'}"


def _rate(numerator: int, denominator: int) -> str:
    """분모가 0이면(그 코드가 아예 등장하지 않으면) 0%가 아니라 '—'로 표시."""
    return f"{numerator / denominator:.0%}" if denominator else "—"


def print_summary(tally: Tally) -> None:
    print("=" * 72)
    print("종합")
    print("=" * 72)
    print(f"  영상 {tally.videos}개 중 rep 수가 정확한 영상: {tally.videos_rep_count_ok}개")
    print(f"  짝지어진 rep: {tally.matched_reps}개 "
          f"(미검출 {tally.missed_reps}, 오검출 {tally.spurious_reps})")
    if tally.matched_reps:
        rate = tally.verdict_ok / tally.matched_reps * 100
        print(f"  판정 일치: {tally.verdict_ok}/{tally.matched_reps} ({rate:.0f}%)")

    if tally.code_stats:
        print("\n  코드별 정확도 (정밀도=엔진이 낸 것 중 맞은 비율, 재현율=라벨에 있는 것 중 잡은 비율)")
        print(f"    {_pad('코드', 24)}{'TP':>4}{'FP':>4}{'FN':>4}{'정밀도':>8}{'재현율':>8}")
        for code in sorted(tally.code_stats):
            tp, fp, fn = tally.code_stats[code]
            print(f"    {_pad(code, 24)}{tp:>4}{fp:>4}{fn:>4}"
                  f"{_rate(tp, tp + fp):>8}{_rate(tp, tp + fn):>8}")


# --- 진입점 --------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(description="라벨 검사 및 엔진 출력 대조")
    parser.add_argument("--exercise", default=DEFAULT_EXERCISE, choices=sorted(EXERCISE_SCHEMA),
                        help=f"검사할 운동 (기본: {DEFAULT_EXERCISE})")
    parser.add_argument("--labels", default=None,
                        help="라벨 JSON 경로(생략하면 운동별 기본 경로)")
    parser.add_argument("--check-only", action="store_true",
                        help="영상을 돌리지 않고 라벨 파일 구조만 검사")
    parser.add_argument("--frame-stride", type=int, default=1,
                        help="N프레임마다 1장 처리(기본 1). 크게 잡으면 최저점을 놓친다")
    parser.add_argument("--model", default=None,
                        help="YOLO pose 가중치 재정의(모델 크기 비교 실험용, 예: yolo11s-pose.pt)")
    args = parser.parse_args()

    labels_rel = args.labels or _schema(args.exercise)["labels_path"]
    labels_path = PROJECT_ROOT / labels_rel
    if not labels_path.exists():
        print(f"라벨 파일이 없습니다: {labels_path}")
        return 2
    entries = json.loads(labels_path.read_text(encoding="utf-8"))

    print("=" * 72)
    print(f"라벨 파일 검사: {labels_rel} (운동 {args.exercise}, 영상 {len(entries)}개)")
    print("=" * 72)
    problems = check_label_file(entries, args.exercise)
    if problems:
        for p in problems:
            print(f"  {p}")
        print(f"\n  라벨 오류 {len(problems)}건 — 고친 뒤 다시 실행하세요.")
        return 1
    print("  라벨 파일 정상 (코드·판정·구간 시각 모두 일관)\n")

    if args.check_only:
        return 0

    found = [(e, PROJECT_ROOT / e["video_path"]) for e in entries]
    missing = [e["video_path"] for e, path in found if not path.exists()]
    found = [(e, path) for e, path in found if path.exists()]

    if not found:
        print("분석할 영상이 하나도 없습니다. 아래 경로에 영상을 넣고 다시 실행하세요.")
        for path in missing:
            print(f"    {path}")
        return 2

    # YOLO 로딩이 무거우므로 실제로 돌릴 영상이 있을 때만 import·초기화한다.
    from ai.engine import analyze_video
    from ai.pose.detector import PoseDetector

    # 모델을 한 번만 로드해 영상마다 재사용. 가중치는 운동별로 다르다.
    from ai.config import pose_model_for

    detector = PoseDetector(args.model or pose_model_for(args.exercise))
    tally = Tally()

    for entry, video_path in found:
        print("=" * 72)
        print(f"영상: {entry['id']}  ({entry['video_path']})")
        print("=" * 72)
        report = analyze_video(
            video_path, exercise=args.exercise,
            save_annotated=False, frame_stride=args.frame_stride, detector=detector,
        )
        for line in compare_video(report, entry, tally):
            print(line)
        print()

    print_summary(tally)
    if missing:
        print(f"\n  영상 파일이 없어 건너뛴 항목 {len(missing)}개:")
        for path in missing:
            print(f"    {path}")
        return 2

    everything_matched = (
        tally.videos_rep_count_ok == tally.videos
        and tally.verdict_ok == tally.matched_reps
        and not tally.missed_reps
        and not tally.spurious_reps
    )
    return 0 if everything_matched else 1


if __name__ == "__main__":
    # 윈도우 콘솔(cp949)에서 한글·기호가 깨지지 않게 한다.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())

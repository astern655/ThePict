"""오프라인 재현기가 프로덕션 rep 카운트와 같은 값을 내는지 검증한다."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path.cwd()))
from rep_lab import count_reps  # noqa: E402

from ai.config import (  # noqa: E402
    PUSHUP_ADAPTIVE_DOWN_RATIO, PUSHUP_ADAPTIVE_MIN_SPAN, PUSHUP_ADAPTIVE_UP_RATIO,
    PUSHUP_ANGLE_SMOOTH_WINDOW, PUSHUP_ELBOW_DOWN_ANGLE, PUSHUP_ELBOW_UP_ANGLE,
    PUSHUP_REP_PROMINENCE,
)

PROD = {  # 프로덕션 실행에서 관측된 rep 수 (validate_labels 2026-08-06 재실행 기준)
    "clip_10280888": 3, "clip_10483840": 3, "clip_27727791": 3, "clip_4742661": 1,
    "clip_4804784": 3, "clip_4804794": 3, "clip_4945123": 5, "clip_4964649": 3,
    "clip_4964650": 3, "clip_5310934": 3, "clip_5802475": 6, "clip_6022762": 3,
    "clip_6970145": 4, "clip_7117537": 3, "clip_7680354": 5, "clip_8343993": 3,
}

params = dict(
    down_ratio=PUSHUP_ADAPTIVE_DOWN_RATIO, up_ratio=PUSHUP_ADAPTIVE_UP_RATIO,
    min_span=PUSHUP_ADAPTIVE_MIN_SPAN, window=PUSHUP_ANGLE_SMOOTH_WINDOW,
    fixed_down=PUSHUP_ELBOW_DOWN_ANGLE, fixed_up=PUSHUP_ELBOW_UP_ANGLE,
    prominence=PUSHUP_REP_PROMINENCE,
)

series_dir = Path(sys.argv[1])
ok = bad = 0
for path in sorted(series_dir.glob("local_*.json")):
    item = json.loads(path.read_text(encoding="utf-8"))
    n, _ = count_reps(item["angles"], item["fps"], **params)
    prod = PROD.get(item["id"])
    mark = "OK " if n == prod else "MISMATCH"
    if n == prod:
        ok += 1
    else:
        bad += 1
    print(f"{mark} {item['id']:<18} 재현기 {n} / 프로덕션 {prod} / 정답 {item['expected_reps']}")
print(f"\n일치 {ok} / 불일치 {bad}")

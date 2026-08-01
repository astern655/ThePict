# 영상이 있어야 진행되는 검증 (보류 목록)

코드로 할 수 있는 준비는 끝났다. 여기 있는 항목들은 **새 영상이 들어와야** 진행된다.
영상이 생기면 이 문서만 보고 이어서 하면 된다.

마지막 갱신: 2026-07-27 · 기준 커밋 시점의 보유 영상 6편(`data/videos/squat_001~006.mp4`)

---

## 0. 지금 당장 할 수 있는 것 (영상은 이미 있음)

**squat_006 라벨링.** 4 rep 전부 깊이 부족 + 상체 과숙임으로 보이는 **유일한 결함 영상**인데
`data/squat_labels.json`에 없다. 지금까지 라벨된 14 rep이 전부 `correct`라, 이 영상이
**재현율(결함을 실제로 잡는가)을 처음 확인할 표본**이다.

> ⚠️ 반드시 **엔진 출력을 보지 않은 상태에서** 프레임만 보고 달 것.
> 엔진 숫자를 보고 라벨을 달면 그 라벨로 계산한 정확도는 아무 의미가 없다.
> (이 문서 작성자는 이미 엔진 출력을 봤으므로 라벨을 달지 않았다.)

---

## 1. 필요한 영상 목록

촬영 조건은 [CAPTURE_AND_SQUAT_CRITERIA.md §3](./CAPTURE_AND_SQUAT_CRITERIA.md) 준수.
**다양성이 개수보다 중요하다** — 같은 사람 10편보다 다른 세 사람 3편이 낫다.

| # | 필요한 영상 | 무엇을 확정하는가 | 우선순위 |
|---|---|---|---|
| A | 피험자 3명 이상 × **명백히 올바른** 측면 rep | 정상 분포 상단 (현재 표본이 사실상 3~4명분뿐) | 높음 |
| B | 피험자별 **명백히 얕은** rep | `SQUAT_GOOD_DEPTH_ANGLE`(90) 재현율, `SEVERE`(110) 경계 | 높음 |
| C | 피험자별 **명백한 굿모닝** rep | `SQUAT_TORSO_SHIN_DIFF_WARN`(30)·`SEVERE`(40) | 높음 |
| D | **정면 촬영** 영상 1편 이상 | `SIDE_VIEW_RATIO_MAX`(0.35)가 정면을 실제로 거르는가 | 높음 |
| E | **45° 대각선** 영상 1편 이상 | 최악 각도가 0.35를 통과해 버리는지 (통과하면 대책 필요) | 중간 |
| F | 상체를 거의 수평까지 접은 rep | `SQUAT_TORSO_LEAN_HARD_MAX`(70) — 근거 없는 유일한 값 | 중간 |
| G | 전신이 프레임을 벗어나는 구간이 있는 영상 | `tracking_gap` / `dropped_rep_count` 실동작 | 낮음 |

D는 라벨 파일에 넣지 않는다 — `validate_labels.py`가 측면 아닌 영상을 거부한다.
`tools/measure_distribution.py`로 비율만 재고 결과를 §4에 적으면 된다.

---

## 2. 영상이 들어오면 실행할 순서

```powershell
$env:PYTHONUTF8="1"

# 1) 분포부터 본다 (라벨 없이)
py -m tools.measure_distribution --json data/output/squat_distribution.json

# 2) 정상 분포 상단과 결함 분포 하단 사이에 임계값이 있는지 확인 → ai/config.py 조정
#    (SQUAT_TUNING.md §5-3)

# 3) 임계값이 확정된 '후에' 라벨을 단다
py -m tools.validate_labels --check-only    # 라벨 파일 일관성
py -m tools.validate_labels                 # 엔진 출력과 대조

# 4) 외부 데이터셋 회귀 확인 (임계값을 바꿨다면 반드시)
py -m tools.evaluate_llm_fms
```

임계값을 바꾸면 `backend/pose_eval.py`의 복제값도 같이 고쳐야 한다
(`backend/test_ai_integration.py`가 두 값의 일치를 검사한다).

---

## 3. 푸시업 — 영상이 아예 없다

푸시업 분석기(`ai/analysis/exercises/pushup.py`)는 규칙과 단위 테스트만 있는 상태다.
**실영상을 한 번도 돌리지 않았고, 임계값 4개 전부 관례값이다**
([PUSHUP_CRITERIA.md §5](./PUSHUP_CRITERIA.md)).

| # | 필요한 영상 | 무엇을 확정하는가 |
|---|---|---|
| P1 | 측면 촬영 **정상** 푸시업 (피험자 3명 이상) | `PUSHUP_ELBOW_DOWN/UP_ANGLE`이 rep을 정확히 세는가, 정상 이탈각 분포 |
| P2 | **얕은** 푸시업(반만 내려감) | `PUSHUP_GOOD_DEPTH_ANGLE`(90) / `SEVERE`(110) |
| P3 | **엉덩이 처진** 푸시업 | `PUSHUP_BODY_LINE_WARN`(15) / `SEVERE`(25), 처짐 방향 판정 |
| P4 | **엉덩이 솟은**(파이크) 푸시업 | 위와 같음, 솟음 방향 판정 |
| P5 | **무릎 대고** 하는 푸시업 | 발목 → 무릎 대체 측정이 실제로 동작하는가 |
| P6 | 머리쪽/발쪽에서 찍은 영상 | 푸시업에서도 `SIDE_VIEW_RATIO_MAX`(0.35)가 통하는가 |

푸시업은 몸이 수평이라 어깨 간격/몸통 길이 비율의 정상 범위가 스쿼트와 다를 수 있다.

**도구는 이미 푸시업을 받는다.** 영상을 `data/videos/pushup_001.mp4` 형식으로 넣고
아래를 그대로 돌리면 된다(라벨 파일은 `data/pushup_labels.json`).

```powershell
py -m tools.measure_distribution --exercise pushup --json data/output/pushup_distribution.json
py -m tools.validate_labels --exercise pushup --check-only
py -m tools.validate_labels --exercise pushup
```

임계값을 정하는 기준과 결정 대기 항목은 [PUSHUP_TUNING.md](./PUSHUP_TUNING.md).

---

## 4. 영상과 무관하게 남아 있는 일 (참고)

이 문서의 범위 밖이지만, 영상 대기 중에 할 수 있는 것들:

- `yolo11n` vs `yolo11s` 같은 영상 측정값 비교 → 키포인트 노이즈와
  `SQUAT_ANGLE_SMOOTH_WINDOW`(3) 적정값
- 영상 길이당 추론 시간 실측 → 백엔드 타임아웃·앱 UX 근거
- NaN 각도 가드, "이게 스쿼트가 맞는가" 검증
  ([INPUT_ROBUSTNESS.md §3](./INPUT_ROBUSTNESS.md))
- 상체 판정 정의를 FMS식 `비평행`으로 넓힐지 결정
  ([LLM_FMS_VALIDATION.md](./LLM_FMS_VALIDATION.md))

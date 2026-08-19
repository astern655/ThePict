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
| C | 피험자별 **명백한 굿모닝** rep | `SQUAT_TORSO_SHIN_DIFF_WARN`(30)·`SEVERE`(40)의 **실영상 재현율** — 지표 자체는 EC3D front_bent AUC 0.948로 검증됨, 남은 건 YOLO 공간 임계 보정뿐 ([SQUAT_TUNING.md §5-5](./SQUAT_TUNING.md)) | 높음 |
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

## 3. 푸시업 — 남은 공백은 몸통 델타 재현율

P1(정상 rep)·P2(얕은 깊이)·P5(무릎)·P6(측면 비율)은 Pexels 16편 + REHAB Ex3 +
PushupBench로 종결됐다([PUSHUP_TUNING.md](./PUSHUP_TUNING.md) §7~§8).
몸통 판정은 2026-08-14 **개인 기준선 캘리브레이션 델타 방식으로 재개**됐고
(§9 재개 4차), 특이도(오탐 0)는 로컬+PushAI로 확인했지만 **재현율(양성)은
미검증**이다. 자기 기준선 방식은 '세트 중 악화'만 잡는 구조라, 필요한 영상이
구체적으로 바뀌었다:

| # | 필요한 영상 | 무엇을 확정하는가 |
|---|---|---|
| P3′ | **곧게 시작(플랭크 2~3초 정지) → 세트 중반부터 엉덩이 처짐** | `PUSHUP_BODY_DELTA_WARN`(15) 재현율 — 델타가 실제 처짐에서 15°를 넘는가 |
| P4′ | 같은 구조로 **엉덩이 솟음**(파이크) 진행 | 솟음(−) 방향 재현율 |
| P7 | 캘리브레이션 없이 시작(동작 중 촬영 시작) | `no_body_baseline` 안내가 사용자를 실제로 교정하는가 (UX 확인) |

⚠️ 촬영 시 반드시 **시작 전 플랭크 정지 구간**을 넣을 것 — 없으면 기준선이
안 잡혀 몸통 판정 자체가 보류된다. 시작부터 처져 있는 영상은 이 방식으로는
잡을 수 없다(기준선에 흡수 — 설계된 한계).

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

# 스쿼트 판정 기준과 튜닝 대상 파라미터

이 문서는 **"지금 숫자를 믿어도 되는가, 못 믿으면 어떻게 고칠 것인가"**를 다룬다.
각 규칙이 무엇을 어떻게 재는지에 대한 설명과 근거는
[CAPTURE_AND_SQUAT_CRITERIA.md](./CAPTURE_AND_SQUAT_CRITERIA.md)에 있다. 여기서는 중복하지 않는다.

> **전제**: 스쿼트는 **측면 촬영 전용**이다. 측면 2D 좌표로 확실히 잴 수 있는
> 깊이·상체 앞숙임 두 가지만 규칙으로 쓴다. 무릎 전방 이동·템포는
> "확실히 잴 수 있는 것만" 원칙에 따라 제거했다(§4.3b of criteria doc).

---

## 1. 현재 판정 기준 한눈에

모든 자세 규칙은 rep **최저점(가장 깊이 앉은 프레임)** 스냅샷으로 판정한다.

| 코드 | 조건 | 심각도 | rep 판정 |
|---|---|---|---|
| `good_depth` | 최저 무릎각 ≤ 90° | GOOD | (판정 안 낮춤) |
| `shallow_depth` | 최저 무릎각 90° 초과 ~ 110° | WARNING | `needs_work` |
| `very_shallow_depth` | 최저 무릎각 > 110° | **ERROR** | `incorrect` |
| `torso_lean` | (상체 − 정강이) 기울기 차 30° 초과 ~ 40° | WARNING | `needs_work` |
| `excessive_torso_lean` | 차 > 40° **또는** 상체 절대 기울기 > 70° | **ERROR** | `incorrect` |

경계값은 **아래 단계에 속한다**(초과일 때만 승급). 정확히 110°면 `shallow_depth`.

rep 판정은 그 rep의 가장 심각한 코드에서 파생된다:
ERROR 있음 → `incorrect` / ERROR 없고 WARNING 있음 → `needs_work` / 둘 다 없음 → `correct`.

영상 수준 코드: `partial_reps`(깊이 부족으로 rep 미인정), `low_detection`(사람 검출률 저조),
`not_side_view`(정면 촬영 의심).

---

## 2. 파라미터 근거 등급

깊이 WARNING 경계는 LLM-FMS 핵심 프레임 270장과 로컬 정상 영상 14 rep로
교차 확인했다. 나머지 파라미터는 대응되는 외부 정답 라벨이 없어 아직 미검증이다.

- **A** — 물리적/기하학적 근거가 문서화됨. 우선순위 낮음.
- **B** — 관례적 기본값. 실패해도 영향이 국소적.
- **C** — 근거 없이 제안된 값. **실데이터로 정해야 함.**

### 2.1 자세 규칙 임계값 (`ai/config.py`)

| 파라미터 | 값 | 등급 | 비고 |
|---|---|---|---|
| `SQUAT_GOOD_DEPTH_ANGLE` | 90.0 | **검증 B** | LLM-FMS 특이도 91.1%, 로컬 정상 14 rep 오탐 0. 데이터셋 단독 최적값 대신 5° 격자·오탐 제약으로 선택 |
| `SQUAT_SEVERE_DEPTH_ANGLE` | 110.0 | 파생 | 심각도 라벨 부재. 검증된 GOOD 경계에서 기존 20° 구간 폭을 유지 |
| `SQUAT_TORSO_SHIN_DIFF_WARN` | 30.0 | 검증 B | 로컬 correct 14 rep 최대 28.7°. 25°에서 발생한 오탐 5건을 제거하는 최소 5° 격자값 |
| `SQUAT_TORSO_SHIN_DIFF_SEVERE` | 40.0 | 파생 | 심각도 라벨 부재. 기존 WARNING→ERROR 구간 폭 10° 유지 |
| `SQUAT_TORSO_LEAN_HARD_MAX` | 70.0 | **C** | 절대 상한 안전장치. 근거 없음 |

### 2.2 반복 카운트 (`ai/config.py`)

| 파라미터 | 값 | 등급 | 비고 |
|---|---|---|---|
| `SQUAT_KNEE_DOWN_ANGLE` | 140.0 | B | 히스테리시스 하단 |
| `SQUAT_KNEE_UP_ANGLE` | 160.0 | B | 히스테리시스 상단 |
| `SQUAT_PARTIAL_DIP_ANGLE` | 150.0 | A | 140·160의 중간값으로 유도됨 |
| `SQUAT_ANGLE_SMOOTH_WINDOW` | 3 | B | 중앙값 필터 윈도. 실영상 노이즈 확인 후 조정 |

### 2.3 영상 품질·촬영 각도 (`ai/config.py`)

| 파라미터 | 값 | 등급 | 비고 |
|---|---|---|---|
| `MIN_KEYPOINT_CONFIDENCE` | 0.5 | B | 이 미만 관절은 계산에서 제외 |
| `MIN_PERSON_RATIO` | 0.5 | B | `low_detection` 발생선 |
| `SIDE_VIEW_RATIO_MAX` | 0.35 | **C** | §4의 구조적 문제 참고 |
| `SIDE_VIEW_MIN_SAMPLES` | 10 | B | 표본 부족 시 판단 보류 |

---

## 3. 튜닝을 막고 있는 것 — 상체 측정값이 기록되지 않는다

**이것부터 고쳐야 나머지가 진행된다.**

`check_depth`는 정상일 때도 `good_depth`(GOOD 등급)를 반환해 `measured`에 무릎각을 남긴다.
게다가 `RepRecord.bottom_angle`에도 같은 값이 들어간다. 그래서 **깊이는 모든 rep에서 측정값을 얻을 수 있다.**

반면 `check_torso`는 정상 범위면 `None`을 반환한다. 상체 기울기·정강이 기울기·둘의 차이가
**어디에도 남지 않는다.** 확인 결과 정상 rep의 리포트에는 `good_depth` 하나뿐이다:

```
정상 rep의 issue 목록:
  good_depth severity=good measured=80.0
RepRecord: bottom_angle=80.0, start_sec=0.1, bottom_sec=0.27, end_sec=0.5, ...
```

즉 **올바른 스쿼트에서 상체−정강이 차가 실제로 몇 도인지 알 방법이 현재 없다.**
LLM-FMS의 비평행 라벨은 현재의 단방향 전방 숙임과 정의가 달라
`SQUAT_TORSO_SHIN_DIFF_WARN`을 직접 학습시키는 정답으로 쓸 수 없다.

### 권장 수정

`RepRecord`에 최저점 측정값을 추가한다. 피드백이 아니라 **측정 데이터**이므로
GOOD 등급 Issue를 하나 더 만드는 것보다 `RepRecord`가 적절하다.

```python
bottom_torso_incline: float | None = None   # 최저점 상체 기울기(수직 기준, 도)
bottom_shin_incline: float | None = None    # 최저점 정강이 기울기(도)
```

`to_dict()`에도 실어 두면 검증 스크립트가 rep마다 분포를 뽑을 수 있다.
`bottom_angle`이 이미 같은 역할을 하고 있으므로 구조상 일관된다.

---

## 4. 구조적 문제 — 측면 자동 검증이 작동하지 않을 수 있음

`_view_ratio`는 **좌우 어깨가 둘 다 보일 때만** 계산된다. 그런데 진짜 측면 촬영에서는
먼 쪽 어깨가 몸에 가려 신뢰도가 `MIN_KEYPOINT_CONFIDENCE`(0.5) 아래로 떨어지기 쉽다.
그러면 표본이 `SIDE_VIEW_MIN_SAMPLES`(10)에 못 미쳐 **검사 자체가 조용히 생략된다.**

정면 영상을 거르는 목적으로는 안전한 방향의 실패다(정면에서는 두 어깨가 잘 보이므로 걸린다).
문제는 **45° 대각선 영상**이다. 깊이·상체 판정이 모두 왜곡되는 최악의 각도인데,
어깨가 애매하게 보여 이 검사를 통과할 수 있다.

실영상으로 확인할 것: 측면 영상에서 `_view_ratio` 표본이 실제로 몇 개나 쌓이는가.
0에 가깝다면 이 검사는 사실상 죽어 있는 것이므로, 다른 지표(예: 발/골반의 좌우 간격)로
바꾸거나 검사 자체를 걷어내야 한다.

---

## 5. 튜닝 절차

### 5-1. 준비 (선행 작업)

1. §3의 `RepRecord` 측정값 추가.
2. 측면 영상 확보 — 다양성이 정확도보다 중요하다.
   - 체형/유연성이 다른 피험자 최소 3명
   - 각자 **명백히 올바른 rep**, **명백히 얕은 rep**, **명백히 굿모닝인 rep**을 의도적으로 수행
   - 촬영 조건은 [CAPTURE_AND_SQUAT_CRITERIA.md §3](./CAPTURE_AND_SQUAT_CRITERIA.md) 준수

### 5-2. 분포 측정

각 영상을 분석해 rep별 (무릎각, 상체−정강이 차)를 모은다. **라벨 없이** 먼저 분포만 본다.
`--frame-stride`는 반드시 1 — 크게 잡으면 최저점 프레임을 놓쳐 측정값이 통째로 틀어진다.

의도적으로 "올바르게" 수행한 rep의 분포가 임계값 안에 들어오는지 확인한다.
올바른 rep의 상체−정강이 차가 기준선 위에 몰려 있다면 `SQUAT_TORSO_SHIN_DIFF_WARN`(30°)이
잘못된 것이다. 현재 로컬 correct 14 rep의 최대값 28.7°를 넘는 최소 5° 격자값으로 잡았다.

### 5-3. 임계값 결정

올바른 rep 분포의 상단과 결함 rep 분포의 하단 사이에 임계값을 둔다.
두 분포가 겹치면 그 지표로는 구분이 안 된다는 뜻이므로, 임계값을 옮길 게 아니라
지표 자체를 재검토해야 한다.

### 5-4. 라벨링 및 검증

임계값이 확정된 **후에** 라벨을 단다. 순서를 뒤집으면 임계값이 바뀔 때마다 라벨을 다시 달아야 한다.

```powershell
python -m tools.validate_labels --check-only   # 라벨 파일 일관성만 검사
python -m tools.validate_labels                # 영상까지 돌려 엔진 출력과 대조
```

라벨 형식과 일관성 규칙은 [data/squat_labels.json](../data/squat_labels.json)과
`tools/validate_labels.py`의 검사 항목을 따른다. `label`은 `feedback_codes`에서
기계적으로 파생되므로 라벨러가 판정을 직접 고민할 필요가 없다.

---

## 6. 결정 대기 항목

| 항목 | 현재 동작 | 결정 필요 |
|---|---|---|
| 깊이는 충분한데 상체만 걸린 rep | `needs_work` | 결함으로 볼 것인가 |
| `torso_lean` WARNING과 `shallow_depth` WARNING이 겹친 rep | `needs_work` (동일) | 두 개 겹치면 승급시킬 것인가 |
| 절대 상한 70° | 정강이와 무관하게 ERROR | 유지할 것인가, 상대 지표만 쓸 것인가 |
| 라벨의 `borderline` 표시 | 미도입 | 경계값 근처 rep을 따로 집계할 것인가 |

**`borderline`**: 임계값 바로 근처(예: 무릎각 98~102°)라 사람도 확신하기 어려운 rep을
라벨에 표시해 두면, 정확도를 그것 포함/제외 두 번 집계할 수 있다.
진짜 오탐과 단순 임계값 오차를 구분하는 데 쓴다.

---

## 7. 미검증 사항

- **실영상 파이프라인 전체.** YOLO 검출 → 각도 계산 → 리포트 경로는 한 번도 실행되지 않았다.
  지금까지의 검증은 전부 합성 관절 좌표 기반이다.
- **실제 키포인트 노이즈에서 무릎각이 몇 도나 흔들리는가.** 이 값이 경계값 근처 rep의
  판정 안정성과 `SQUAT_ANGLE_SMOOTH_WINDOW` 적정값을 결정한다.
- **rep 매칭의 탐욕적 할당.** `tools/validate_labels.py`의 `match_reps`는 최적 할당이 아니라
  라벨 순서대로 겹침이 가장 큰 엔진 rep을 집어간다. 실영상에서 rep 경계가 크게 어긋날 때
  짝이 밀릴 수 있다.

---

## 8. 요약 — 작업 순서

1. `RepRecord`에 상체·정강이 기울기 기록 추가 (§3) ← **선행 필수**
2. 측면 영상 확보, 실영상 파이프라인 첫 실행 (§7)
3. 분포 측정 후 C 등급 임계값 5개 확정 (§2.1, §5)
4. 측면 자동 검증이 실제로 동작하는지 확인 (§4)
5. 임계값 확정 후 라벨링 → `tools/validate_labels.py`로 대조 (§5-4)

# rep 카운트 튜닝 실험대

푸시업 반복 카운트 파라미터를 **YOLO 재실행 없이** 실험하기 위한 도구 모음이다.
근거와 진단 결과는 [docs/PUSHUP_TUNING.md](../../docs/PUSHUP_TUNING.md) §7-A-1, §7-A-2.

## 왜 캐시가 필요한가

파라미터를 하나 바꿀 때마다 영상 26편에 YOLO를 다시 돌리면 회당 30분~수 시간이
걸린다. 팔꿈치각 시계열만 한 번 떠 두면 격자 탐색이 초 단위로 끝난다.

## 순서

```powershell
$env:PYTHONUTF8="1"
# 1) 각도 시계열 캐시 (영상별 증분 저장 — 중단해도 이어서 실행됨)
py -3 tools/experiments/cache_series2.py data/output/series both

# 2) 오프라인 재현기가 프로덕션과 같은 값을 내는지 먼저 확인 (필수)
py -3 tools/experiments/verify_replica.py data/output/series

# 3) 개별 영상 진단 (텍스트 스파크라인 + 적응 임계 표시)
py -3 tools/experiments/diagnose_series.py data/output/series/local_clip_27727791.json

# 4) 두 세트를 함께 놓고 파라미터 탐색 (로컬만 보면 안 된다 — 아래 규칙)
py -3 tools/experiments/joint_search.py data/output/series

# 5) 후보 선택까지 포함한 일반화 확인
py -3 tools/experiments/joint_loo.py data/output/series

# 6) 후보 계열 간 영상 단위 비교 (총오차 + 최악 오차)
py -3 tools/experiments/compare_families.py data/output/series

# 보조) 특정 실패 클립이 파라미터로 고쳐지는지 전수 조사
py -3 tools/experiments/failure_probe.py data/output/series
```

캐시는 `data/output/series/`에 25편(로컬 16 + REHAB 9) 확보돼 있다.
탐색 결과와 채택 근거(깊이 가드로 무회귀 달성, 2026-08-06 적용 완료)는
[PUSHUP_TUNING.md §7-A-3](../../docs/PUSHUP_TUNING.md). 파라미터를 다시 만질
때는 **가드 축(prominence·min_rep_sec)을 격자에 포함**할 것 — 가드 없는
격자는 PM_121류(임계선을 스치는 얕은 dip) 회귀를 못 본다.

`rep_lab.py`의 `count_reps()`가 프로덕션 경로(중앙값 필터 → 적응 임계 →
히스테리시스 → 유실 폐기)를 재현한다. `evaluate()`로 세트 전체 성적을 낸다.

## 규칙

- **재현기 검증(2단계)을 건너뛰지 말 것.** 재현기가 프로덕션과 어긋나면 이후
  튜닝은 전부 무의미하다. 현재 확인분: 로컬 3/3 일치.
- **로컬(깨끗한 영상)과 REHAB(재활 환경)을 동시에 봐야 한다.** 실제로 로컬에서
  파레토 개선(14→15/16, 깨진 편 0)이던 후보가 REHAB PM_121을 **11→23**으로
  파괴한 사례가 있다. 한쪽만 보고 파라미터를 옮기면 다른 쪽이 무너진다.
- **평활 윈도(window)를 격자에서 빼지 말 것.** 이 축을 빠뜨려 "기준선을 못
  넘는다"는 잘못된 결론에 도달할 뻔했다.
- **총오차만 보지 말고 최악 영상 오차를 함께 볼 것.** 평균이 좋아지면서 특정
  영상이 파국적으로 틀리는 선택을 걸러낸다.
- 캐시 실행 중에 대용량 다운로드를 같이 돌리지 말 것 — 디스크 경합으로 YOLO
  처리량이 1/20까지 떨어진 사례가 있다.
- `torch.set_num_threads`로 스레드를 줄이지 말 것 — 5배 느려졌다(기본값이 맞다).

## 몸통 캘리브레이션 실험 (2026-08-14)

rep 카운트와 별도로, 몸통 기준선·δ 임계 실험용 캐시와 실험대가 있다:

```powershell
# 프레임 캐시: [idx, 팔꿈치각, 이탈각, 방향] (로컬 16 + PushAI 100, 증분 저장)
py -3 tools/experiments/cache_pushup_body.py data/output/series_body both
# 클립별 진단 / 기준선 전략 × δ 격자 / PushAI 운영점 평가
py -3 tools/experiments/body_lab.py data/output/series_body diag
py -3 tools/experiments/body_lab.py data/output/series_body grid
py -3 tools/experiments/body_lab.py data/output/series_body pushai
```

채택 운영점(꼬리15 + sd≤6 게이트 + δ15/25)의 근거는
[PUSHUP_TUNING.md §9 재개 4차](../../docs/PUSHUP_TUNING.md). 기준선 전략을
다시 만질 때는 **격자에 안정 게이트 축을 포함**할 것 — 게이트 없는 격자는
측정 표류 클립(5802475·10483840류)의 오탐을 δ로 덮으려다 감도를 잃는다.

## 알려진 처리 불가 영상

- `PM_010`(REHAB Ex3, 4071프레임): 배경에 추가 인물이 있어 추적이 폭주,
  3000프레임 부근에서 사실상 정지. 과다 카운트(16→26) 사례라 진단 가치가
  높지만 현재 장비로는 처리하지 못했다.

# 진행 로드맵 & 체크리스트

> 개념은 [`ARCHITECTURE.md`](./ARCHITECTURE.md) 참고. 이 문서는 "무엇을 어디까지 했나"를 추적합니다.

## 마일스톤

### M0. AI 엔진 큰 틀 (완료 ✅)
- [x] 아키텍처 문서 작성 (`ARCHITECTURE.md`) — 3계층(프론트/백엔드/AI) 구조 반영
- [x] `ai/` 패키지 구조 생성 (pose / analysis / video / engine / cli)
- [x] 공개 진입점 `ai.analyze_video()` 구현
- [x] `requirements.txt` 정리
- [x] YOLO 가중치 다운로드 & 관절 검출 동작 확인 (`smoke_detector`)
- [x] AI 로직 단독 검증 통과 (`test_squat_logic`: 각도·rep카운트·깊이판정)
- [ ] **실제 스쿼트 영상으로 엔드투엔드 1회** ← 사용자 샘플 영상 필요

### M1. 스쿼트 MVP (AI 부분)
- [ ] 실제 영상에서 rep 카운트 정확도 확인 및 임계값 튜닝
- [ ] 깊이/무릎모임/상체숙임 규칙 튜닝
- [ ] 주석 영상 출력 육안 확인

### M2. 백엔드
- [ ] FastAPI 서버: 영상 업로드 엔드포인트
- [ ] `analyze_video()` 호출 → 리포트 JSON 반환
- [ ] 모델 1회 로드 후 재사용(PoseDetector 주입)
- [ ] 주석 영상 정적 파일 서빙

### M3. 프론트엔드
- [ ] 업로드 화면 + 진행 표시
- [ ] 리포트(반복 수·피드백) 표시
- [ ] 주석 영상 재생

### M4. 확장
- [ ] 두 번째 운동 추가 (푸시업 or 런지)
- [ ] 결함 발생 프레임 썸네일
- [ ] confidence 낮은 프레임 자동 스킵/보간

### M3. 고도화 (선택)
- [ ] 실시간 웹캠 모드
- [ ] 좌/우 대칭성 분석
- [ ] 리포트 PDF 내보내기

## 현재 상태 메모
- **2026-07-29: 스쿼트 깊이 1차 지표를 무릎각→대퇴 거상각(30°/50°)으로 교체.**
  근거는 [LLM_FMS_VALIDATION.md](./LLM_FMS_VALIDATION.md) §깊이 지표 교체
  (LLM-FMS 재현율 55.7%→74.7%, EC3D 교차 검증 `tools/evaluate_ec3d.py`).
  무릎각 90°/110°는 스냅샷 유실 시 예비. 라벨 검증 판정 일치 14/14 유지.
  ⚠️ squat_002 부분 반복(라벨 1 / 엔진 0) 불일치가 관측됨 — 깊이 교체와 무관한
  무릎각 카운트 경로. 원인 미조사.
- Python 3.14.6 / torch 2.12.1 / ultralytics 8.4.84 설치 확인됨.
- `yolo11n-pose.pt` 다운로드 완료 → `models/`에 보관.
- ⚠️ 이 PC에서 `python`은 Store 스텁이라 안 됨 → **`py`** 사용.
- ⚠️ 한글/이모지 출력 시 `$env:PYTHONUTF8="1"` 필요.

## 실행 방법 (현재)
```powershell
$env:PYTHONUTF8="1"
py -m tests.test_squat_logic     # AI 로직 검증 (모델 불필요, 즉시)
py -m tests.smoke_detector       # YOLO 연동 확인
py -m ai.cli <영상경로>          # 실제 영상 분석 → data/output/에 주석 영상
```

## 다음 액션

> ⚠️ 위 체크리스트는 M0 시점 기준이라 오래됐다. 백엔드(M2)·앱(M3)은 이미 붙어 있고
> 실영상 파이프라인도 돌고 있다. 현재 상태는 아래 문서를 본다.

1. **모델 검증의 병목은 영상 데이터다** → [PENDING_VIDEO_WORK.md](./PENDING_VIDEO_WORK.md)
2. 임계값 근거·미검증 항목 → [SQUAT_TUNING.md](./SQUAT_TUNING.md)
3. 분포 재측정: `py -m tools.measure_distribution`

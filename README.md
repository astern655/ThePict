# Hohowatt

YOLO-pose 기반 헬스 자세 교정 앱. 운동 영상을 분석해 **반복 횟수**와 **회차별
자세 판정**(올바름/교정 필요/잘못됨)을 내고, 세트·휴식을 관리하며, 운동 후
**문장으로 된 자세 피드백**을 준다.

분석하는 운동: **스쿼트**, **푸시업** (둘 다 측면 촬영 전용)

- **프론트엔드**: Flutter (`app/`)
- **백엔드**: FastAPI + SQLite (`backend/`)
- **AI 엔진**: YOLO Pose + 운동별 규칙 (`ai/`) — 실제 자세 판정은 전부 여기서 한다

## 구조

```
ai/        AI 엔진 (관절 검출·반복 카운트·자세 규칙·리포트 생성)
backend/   FastAPI 서버 (인증·세션·프로그램·AI 엔진 호출)
app/       Flutter 앱 (화면·위젯·API 클라이언트)
tests/     AI 엔진 테스트
tools/     라벨 검증 등 개발 도구
docs/      요구분석·서비스 구조·촬영/판정 기준 문서
data/      입력 영상과 분석 산출물 (커밋하지 않음)
models/    YOLO 가중치 (커밋하지 않음, 최초 실행 시 자동 다운로드)
```

## 백엔드와 AI 엔진의 관계

백엔드는 AI 엔진을 두 경로로 쓴다. 접합부는 `backend/ai_bridge.py` 하나뿐이다.

| 엔드포인트 | 입력 | 하는 일 |
|---|---|---|
| `POST /inference/pose` | 프레임 1장 | 관절 좌표 + 그 순간의 각도 판정 (실시간 오버레이용) |
| `POST /inference/video` | 영상 1편 | AI 엔진 전체 분석 — 반복 횟수, 회차별 판정, 측면 촬영 검증 |

`/inference/video` 응답의 `set` 은 그대로 `POST /sessions` 의 `sets[0]` 에 넣을 수
있고, 그러면 기존 문장 분석(`GET /sessions/{id}/analysis`)이 그대로 이어진다.

**영상은 측면 촬영만 받는다.** 정면 영상은 깊이·상체 판정이 부정확해서 리포트에
경고가 붙는다. 근거와 촬영 가이드: 스쿼트는 `docs/CAPTURE_AND_SQUAT_CRITERIA.md`,
푸시업은 `docs/PUSHUP_CRITERIA.md`.

⚠️ **푸시업 임계값은 아직 실영상으로 검증되지 않았다**(관례값).
검증에 필요한 영상 목록: `docs/PENDING_VIDEO_WORK.md`.

## 실행

### 1. 백엔드 (먼저)

```bash
pip install -r requirements.txt          # AI 엔진 (ultralytics/opencv/numpy)
pip install -r backend/requirements.txt  # 서버 (fastapi 등)

cd backend
cp .env.example .env          # 필요 시 값 수정
python -m uvicorn main:app --port 8000
```

`http://localhost:8000` 에서 뜬다. 첫 실행 시 SQLite DB(`hohowatt.db`)가 자동 생성된다.
AI 의존성을 깔지 않아도 서버는 뜨고, `/inference/video` 만 503을 낸다.

### 2. 앱

```bash
cd app
flutter pub get
flutter run -d chrome --web-port 5555
```

Windows에서는 루트의 `run-backend.bat` / `run-app.bat` 을 더블클릭해도 된다(백엔드 먼저).

### AI 엔진 단독 실행

서버 없이 영상 하나만 분석해 보려면:

```bash
python -m ai.cli data/videos/squat_001.mp4
```

## 환경 변수 (backend)

`backend/.env.example` 참고. 핵심:

| 변수 | 기본 | 설명 |
|---|---|---|
| `HOHOWATT_DB` | `backend/hohowatt.db` | SQLite 경로 |
| `POSE_ESTIMATOR` | `stub` | `stub` \| `yolo` — `/inference/pose` 가 쓸 추정기 |
| `YOLO_POSE_WEIGHTS` | `ai/config.py`의 `POSE_MODEL` | YOLO 가중치 경로 |

`stub`은 더미 키포인트를 내는 개발용이다. 각도 계산·판정 로직(`pose_eval.py`)은
실제로 돌지만 좌표가 가짜다. `yolo`로 두면 `ai/pose/detector.py`의 실제 모델을 쓴다.
`/inference/video` 는 이 설정과 무관하게 항상 AI 엔진을 쓴다.

## 테스트

```bash
python -m pytest tests -q              # AI 엔진 (루트에서)
cd backend && python -m pytest -q      # 백엔드
cd app && flutter test                 # 앱
```

백엔드 테스트는 AI 의존성 없이도 전부 돈다 — 엔진이 필요한 항목은 skip된다.
CI(`.github/workflows/backend.yml`)는 백엔드만 돌리므로, AI 엔진 변경은 로컬에서
`pytest tests` 로 확인한다.

## 튜닝

자세 판정 임계값은 전부 `ai/config.py` 한 곳에 있다. 판정 기준과 근거는 운동별로:

| 운동 | 판정 기준 | 임계값 근거·튜닝 |
|---|---|---|
| 스쿼트 | `docs/CAPTURE_AND_SQUAT_CRITERIA.md` | `docs/SQUAT_TUNING.md` |
| 푸시업 | `docs/PUSHUP_CRITERIA.md` | `docs/PUSHUP_TUNING.md` |

실영상 분포를 다시 뽑으려면:

```bash
python -m tools.measure_distribution --exercise squat
```

`backend/pose_eval.py`의 `squat_depth_max` / `torso_shin_diff_max` 는 `ai/config.py`
값을 복사한 것이다. 엔진 쪽을 바꾸면 여기도 바꿔야 하며,
`backend/test_ai_integration.py` 가 두 값의 일치를 검사한다.

## 폰트

`app/fonts/`의 Pretendard는 SIL Open Font License 1.1 이다.
원본: https://github.com/orioncactus/pretendard

## 주의

- `hohowatt.db`, `.env` 는 커밋하지 않는다(`.gitignore` 처리됨). DB에는 계정과
  비밀번호 해시가 들어 있다.
- 비밀번호는 PBKDF2-SHA256 해시로 저장된다. 토큰은 DB 기반 세션 토큰이다.
- `/inference/video` 는 업로드를 100MB로 제한하고, 분석 후 임시 파일을 지운다.
  주석 영상(`data/output/`)은 서버 응답에 경로를 싣지 않는다.

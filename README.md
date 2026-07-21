# Hohowatt

YOLO-pose 기반 헬스 자세 교정 모바일 앱. 카메라로 운동 자세를 추정해 관절 각도를
평가하고, 세트/휴식을 관리하며, 운동 후 **문장으로 된 자세 피드백**을 제공한다.

- **프론트엔드**: Flutter (`app/`)
- **백엔드**: FastAPI + SQLite (`backend/`)
- **자세 추정**: YOLO-pose 어댑터 (`backend/pose_estimator.py`, 기본은 스텁)

## 구조

```
app/       Flutter 앱 (화면·위젯·API 클라이언트)
backend/   FastAPI 서버 (인증·세션·자세 판정·분석)
docs/      요구분석·서비스 구조 문서
```

## 실행

### 1. 백엔드 (먼저)

```bash
cd backend
pip install -r requirements.txt
cp .env.example .env          # 필요 시 값 수정
python -m uvicorn main:app --port 8000
```

`http://localhost:8000` 에서 뜬다. 첫 실행 시 SQLite DB(`hohowatt.db`)가 자동 생성된다.

### 2. 앱

```bash
cd app
flutter pub get
flutter run -d chrome --web-port 5555
```

Windows에서는 루트의 `run-backend.bat` / `run-app.bat` 을 더블클릭해도 된다
(백엔드 먼저).

## 환경 변수 (backend)

`.env.example` 참고. 핵심:

| 변수 | 기본 | 설명 |
|---|---|---|
| `HOHOWATT_DB` | `backend/hohowatt.db` | SQLite 경로 |
| `POSE_ESTIMATOR` | `stub` | `stub` \| `yolo` |
| `YOLO_POSE_WEIGHTS` | — | `yolo`일 때만, 학습 가중치 경로 |

`stub`이어도 각도 계산·자세 판정 로직(`pose_eval.py`)은 실제로 동작한다.
키포인트만 더미다. 실제 YOLO 모델은 `pose_estimator.py`의 `YoloPoseEstimator`
안내대로 연결한다.

## 테스트

```bash
cd backend && python -m pytest -q      # 백엔드
cd app && flutter test                 # 앱
```

## 폰트

`app/fonts/`의 Pretendard는 SIL Open Font License 1.1 이다.
원본: https://github.com/orioncactus/pretendard

## 주의

- `hohowatt.db`, `.env` 는 커밋하지 않는다 (`.gitignore` 처리됨). DB에는 계정과
  비밀번호 해시가 들어 있다.
- 비밀번호는 PBKDF2-SHA256 해시로 저장된다. 토큰은 메모리/DB 기반 세션 토큰이다.

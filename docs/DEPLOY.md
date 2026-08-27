# 배포 가이드 — 백엔드(Render) + 앱(APK)

## A. 백엔드를 Render에 올리기

### 1) Blueprint로 배포 (권장)
1. 저장소를 GitHub에 푸시한다(이미 됨).
2. Render 대시보드 → **New +** → **Blueprint** → 이 저장소 선택.
3. 루트의 `render.yaml`을 자동 인식한다. **Apply**.
4. 첫 배포가 끝나면 URL이 나온다: `https://thefit-backend.xxxx.onrender.com`

### 2) 수동 설정으로 배포 (Blueprint 대신)
**New +** → **Web Service** → 저장소 선택 후:
- **Root Directory**: `backend`
- **Runtime**: Python 3
- **Build Command**: `pip install -r requirements.txt`
- **Start Command**: `uvicorn main:app --host 0.0.0.0 --port $PORT`
- **Health Check Path**: `/health`
- **Environment**: `PYTHON_VERSION=3.11.9`, `POSE_ESTIMATOR=stub`

### 3) 배포 확인
```
curl https://<당신-URL>/health      # {"status":"ok"}
curl https://<당신-URL>/exercises   # 운동 목록 JSON
```

### 무료 티어에서 도는 범위
- **동작**: 회원가입/로그인, 프로필, 세션 기록/조회, 캘린더, 비교, 프로그램(세트/휴식), 문장 분석.
- **503을 내는 것**: `/inference/video`, `/inference/stream` — 무거운 AI 엔진(torch/ultralytics/
  opencv)은 무료 티어에 설치하지 않는다(메모리·빌드시간 초과, 애초에 GPU가 필요).

### ⚠️ 데이터 휘발성 (중요)
무료 티어는 디스크가 휘발성이다. **재배포하거나, 15분 유휴 후 슬립→콜드스타트 하면
SQLite DB(계정·기록)가 초기화된다.** APK 연결 테스트·데모엔 문제없지만, 계정을 유지하려면:
- (a) 유료 인스턴스 + **Render Disk**를 붙이고 `HOHOWATT_DB`를 마운트 경로로 지정, 또는
- (b) **Render 무료 Postgres**로 이전 — `backend/db.py`를 sqlite3 → Postgres로 바꿔야 한다(요청 시 작업).

---

## B. 앱을 APK로 빌드하기

앱에는 지금 `web/` 플랫폼만 있다. Android를 먼저 생성한 뒤 빌드한다.

### 1) Android 플랫폼 생성 (최초 1회)
```bash
cd app
flutter create --platforms=android .
```

### 2) 인터넷 권한 추가 (릴리스 APK 필수)
`app/android/app/src/main/AndroidManifest.xml`의 `<manifest>` 안, `<application>` 위에 추가:
```xml
<uses-permission android:name="android.permission.INTERNET"/>
```
> Render는 HTTPS라 cleartext 설정은 필요 없다. (로컬 http 백엔드로 테스트할 때만
> `android:usesCleartextTraffic="true"`가 추가로 필요하다.)

### 3) 백엔드 URL을 박아 빌드
앱은 `API_BASE_URL` 컴파일 상수를 읽는다(`app/lib/api.dart`). Render URL을 넘긴다:
```bash
flutter build apk --release --dart-define=API_BASE_URL=https://<당신-URL>
```
결과물: `app/build/app/outputs/flutter-apk/app-release.apk`

### 4) 설치
APK를 기기로 옮겨 설치하거나:
```bash
flutter install --dart-define=API_BASE_URL=https://<당신-URL>
```

### 참고
- 백엔드 주소를 안 넘기면 기본값 `http://localhost:8000`이라 실기기에서 서버를 못 찾는다.
  APK 빌드 때 `--dart-define`을 **반드시** 넘길 것.
- 에뮬레이터에서 로컬 백엔드로 테스트하려면 호스트가 `10.0.2.2`:
  `--dart-define=API_BASE_URL=http://10.0.2.2:8000` + cleartext 허용.

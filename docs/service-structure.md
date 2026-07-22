# 서비스 구조도 — YOLO-pose 헬스 자세 교정 앱

- 버전: v0.2 (2026-07-17)
- 기반 문서: [requirements.md](./requirements.md) v0.3 (F11~F13 추가, Q4 "계정 도입" 확정 반영)
- 전제: **Q1(추론 위치)·Q14(저장 전략)·Q15(인증 방식)는 미확정.** 아래 구조는 기획팀 권장안 — **온디바이스 추론 + 서버 인증/프로필(필수) + 세션 기록 로컬 우선·서버 동기화** — 를 기본으로 그렸다. v0.1의 "서버 없는 MVP"는 로그인 도입 확정으로 폐기됨.

---

## 1. 전체 서비스 구조

```mermaid
flowchart TB
    subgraph App["Flutter 앱 (모바일)"]
        direction TB
        subgraph Onboard["계정·기초 (v0.2 신규)"]
            Login["로그인/온보딩<br/>Apple·Google·이메일 (F12)"]
            Profile["프로필/설정<br/>신체정보·계정삭제 (F13)"]
            Guide["운동 가이드<br/>동작·주의사항, 로컬 번들 (F11)"]
        end
        subgraph UI["운동·기록 화면"]
            Home["홈 / 운동 선택<br/>(F7)"]
            Workout["운동 화면<br/>카메라 + 스켈레톤 오버레이<br/>+ 음성 피드백 (F1·F4)"]
            Summary["세션 요약 화면<br/>(F6)"]
            Calendar["캘린더 뷰<br/>날짜별 기록 (F10)"]
            Compare["일간 비교 카드<br/>어제 vs 오늘 (F9)"]
        end
        subgraph Pipeline["온디바이스 AI 파이프라인"]
            Capture["프레임 캡처<br/>(F1)"]
            Pose["YOLO-pose 추론 (tflite)<br/>관절 키포인트 추출 (F2)"]
            Eval["자세 평가<br/>각도·정렬 규칙, 폼 점수 (F3)"]
            Rep["렙 카운터<br/>(F5)"]
        end
        subgraph Data["데이터 계층"]
            Repo["기록 저장소 (Repository)"]
            LocalDB[("로컬 DB (우선 저장)<br/>날짜별 세션 기록")]
            Sync["동기화 관리자<br/>(백그라운드, Q14)"]
        end
    end

    subgraph Server["FastAPI 서버 (MVP 필수 — v0.2 승격)"]
        Auth["인증 API<br/>토큰 발급/검증 (F12)<br/>(관리형 Auth 여부 Q15)"]
        ProfileAPI["프로필 API (F13)<br/>계정/데이터 삭제 포함"]
        SyncAPI["세션 동기화 API<br/>백업·기기 이관 (F6·Q12)"]
        ServerDB[("서버 DB<br/>계정·프로필·세션 백업")]
        InferAPI["추론 API (F8)<br/>(조건부 — Q1·Q2 결정 시)"]
    end

    Login --> Home
    Login -- "온보딩 프로필" --> Profile
    Home --> Guide
    Home --> Workout
    Workout --> Capture --> Pose --> Eval
    Eval --> Rep
    Eval -- "즉시 피드백<br/>(오버레이·색상·음성)" --> Workout
    Rep -- "렙 수 표시" --> Workout
    Eval -- "세트별 폼 점수" --> Repo
    Rep -- "세트별 렙 수" --> Repo
    Repo --> LocalDB
    Repo --> Sync
    Workout -- "세션 종료" --> Summary
    Summary --> Compare
    Repo -- "날짜별 조회" --> Calendar
    Repo -- "어제/직전 세션 집계" --> Compare

    Login -- "HTTPS" --> Auth
    Profile -- "HTTPS" --> ProfileAPI
    Sync -- "HTTPS (연결 시)" --> SyncAPI
    Auth --> ServerDB
    ProfileAPI --> ServerDB
    SyncAPI --> ServerDB
    App -. "조건부 (녹화 리뷰·서버 추론)" .-> InferAPI
    style InferAPI stroke-dasharray: 5 5
```

핵심 원칙 (v0.2):
- **실시간 루프(F1→F2→F3→F4)는 여전히 전부 기기 안에서 돈다** — 서버가 MVP에 들어왔지만 인증·프로필·동기화 용도일 뿐, 추론은 온디바이스 유지(Q1 권장안). **영상 원본은 서버로 전송하지 않는다** (프라이버시·대역폭·비용).
- **세션 기록은 로컬 우선 저장 + 백그라운드 서버 동기화** (Q14 권장안) — 헬스장 네트워크가 불안정해도 기록·조회 가능(Q10), 로그인 계정으로 백업·기기 이관(Q12 해소).
- **추론 API(F8)만 조건부로 남는다** — 녹화 정밀 리뷰(시나리오 B)나 서버 추론 채택 시에만.

## 2. 실시간 코칭 데이터 흐름 (시나리오 A)

```mermaid
sequenceDiagram
    actor U as 사용자
    participant W as 운동 화면 (F1·F4)
    participant P as YOLO-pose (F2)
    participant E as 자세 평가 (F3)
    participant R as 렙 카운터 (F5)
    participant D as 로컬 DB (F6)
    participant S as 서버 동기화 (F6·Q14)

    U->>W: 운동 선택 후 시작 (F7, 필요 시 가이드 F11 확인)
    loop 매 프레임 (실시간, 전부 온디바이스)
        W->>P: 카메라 프레임
        P->>E: 관절 키포인트 + 신뢰도
        E->>E: 각도·정렬 계산, 정상/경고 판정
        E-->>W: 스켈레톤 오버레이 + 문제 관절 강조
        alt 잘못된 자세
            E-->>U: 음성 피드백 ("무릎이 너무 앞으로 나왔어요")
        end
        E->>R: 동작 상태
        R-->>W: 렙 카운트 갱신
    end
    U->>W: 세트/세션 종료
    W->>D: 세션 기록 저장 (날짜·운동·세트·렙·폼 점수)
    D-->>W: 세션 요약 + 어제 대비 비교 (F9)
    D--)S: 백그라운드 동기화 (네트워크 연결 시)
```

## 3. 첫 사용(온보딩) 흐름 (시나리오 D — v0.2 신규)

```mermaid
sequenceDiagram
    actor U as 사용자
    participant A as Flutter 앱
    participant Auth as FastAPI 인증 (F12)
    participant DB as 서버 DB

    U->>A: 앱 설치 후 실행
    A->>U: 로그인 화면 (Apple / Google / 이메일)
    U->>A: 소셜 로그인 선택
    A->>Auth: 소셜 토큰 검증 요청
    Auth->>DB: 계정 생성/조회
    Auth-->>A: 액세스 토큰 발급 (재실행 시 세션 유지)
    A->>U: 온보딩 (성별·나이·키·몸무게·목표)
    U->>A: 입력 완료
    A->>Auth: 프로필 저장 (F13)
    Auth->>DB: 프로필 기록
    A->>U: 홈 진입 → 운동 가이드(F11)·첫 운동 시작
```

## 4. 기록·비교·캘린더 데이터 흐름 (시나리오 C)

```mermaid
flowchart LR
    F5["F5 렙 카운팅"] --> F6
    F3["F3 폼 점수"] --> F6
    F6[("F6 세션 기록<br/>로컬 우선 저장")] --> F10["F10 캘린더<br/>월간 뷰·날짜 마킹"]
    F6 --> F9["F9 일간 비교<br/>렙·폼 점수·운동량 증감"]
    F6 -. "백그라운드 동기화 (Q14)" .-> SDB[("서버 DB<br/>백업·기기 이관")]
    F10 -- "날짜 선택" --> Detail["해당일 세션 상세"]
```

- F9와 F10은 **서로 의존하지 않는다** — 둘 다 F6에만 의존. (구현 순서 권고: F12 → F6 → F10 → F9)
- 세션의 소속 날짜는 **시작 시각의 기기 로컬 시간대 기준**으로 기록 시점에 확정 (requirements.md F10 수용 기준).

## 5. 기능 의존 그래프 (전체)

```mermaid
flowchart TB
    F12["F12 로그인/온보딩"] --> F13["F13 프로필/설정"]
    F12 -.-> Sync["F6 서버 동기화<br/>(계정 필요)"]
    F7["F7 운동 선택·홈"] --> F1["F1 카메라·프레임 캡처"]
    F7 --> F11["F11 운동 가이드"]
    F1 --> F2["F2 YOLO-pose 키포인트"]
    F2 --> F3["F3 자세 평가·폼 점수"]
    F3 --> F4["F4 실시간 피드백<br/>오버레이·음성"]
    F3 --> F5["F5 렙 카운팅"]
    F3 --> F6["F6 세션 기록 (로컬)"]
    F5 --> F6
    F6 --> F10["F10 캘린더"]
    F6 --> F9["F9 일간 비교"]
    F6 -.-> Sync
    F8["F8 백엔드 추론 API<br/>(조건부)"] -.-> F2
    style F8 stroke-dasharray: 5 5
    style F9 fill:#fff3cd
    style F10 fill:#fff3cd
    style F11 fill:#d1e7dd
    style F12 fill:#d1e7dd
    style F13 fill:#d1e7dd
```

- 노란색: 사용자 추가 요청 (F9·F10) / 초록색: 기초 기능 표준화로 추가 (F11~F13, v0.2)
- 점선: 조건부 또는 계정 전제

## 6. 구조가 바뀌는 분기점 (열린 질문과의 연결)

| 결정 | 선택지 | 구조 변화 |
|---|---|---|
| ~~Q4 계정~~ | **도입으로 확정** | FastAPI 서버(인증·프로필·동기화) + 서버 DB가 MVP 필수 편입 — 본 문서 v0.2에 반영됨 |
| Q1 추론 위치 | 온디바이스 (권장) | 위 기본 구조 그대로 — 추론 API(F8) 불필요 |
| | 서버 추론 | F2·F3이 FastAPI로 이동, 실시간성 저하 — 시나리오 B 중심으로 재편 |
| | 하이브리드 | 파이프라인 2개 (실시간=온디바이스, 정밀 리뷰=서버) |
| Q2 녹화 리뷰 포함 | 포함 | F8 + 영상 업로드·분석 결과 화면 추가 |
| Q14 저장 전략 | 로컬 우선+동기화 (권장) | 위 기본 구조 그대로 — 오프라인 지원, Q12 해소 |
| | 서버 단독 | 로컬 DB·동기화 관리자 제거, 대신 오프라인 기록/조회 불가 (Q10 충돌) |
| Q15 인증 방식 | 관리형 Auth | 인증 API가 외부 서비스 연동 계층으로 축소, 개발 부담 감소 |
| | 자체 구현 | FastAPI에 토큰 발급·소셜 검증·세션 관리 전체 구현 |

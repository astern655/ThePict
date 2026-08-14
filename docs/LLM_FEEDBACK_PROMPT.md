# LLM 코칭 피드백 — 프롬프트 엔지니어링 명세 (연동 전 준비물)

지금 피드백은 규칙 기반 템플릿(`backend/analysis.py`, `ai/analysis/feedback.py`)이다.
정확하지만 문장이 딱딱하고 다양성이 없다. LLM으로 **문장을 자연스럽게** 바꾸되,
**판정은 그대로 규칙 엔진이 한다.** 이 문서는 그 LLM 연동에 쓸 프롬프트를 미리 굳혀둔 것이다.

## 대원칙 — LLM은 판정하지 않는다, 문장만 만든다

- 자세 판정(관절 각도 vs 임계값, 반복 카운트)은 **YOLO + 규칙 엔진이 이미 정확히** 한다.
- LLM은 **픽셀·영상을 절대 안 본다.** 엔진이 뽑은 **구조화된 수치·판정만** 입력으로 받는다.
- LLM의 유일한 일: 그 수치를 **따뜻하고 자연스러운 한국어 코칭 문장**으로 바꾸는 것(rephrase/synthesize).
- → 입력에 없는 사실을 지어내면 환각. **입력에 없는 수치·관절·판정을 만들지 못하게** 강하게 제약한다.

이 구조라 규칙 기반의 정확성(수치 근거)과 LLM의 자연스러움을 둘 다 얻는다.

## 모델·파라미터 (권장 기본값)

- 모델: `claude-haiku-4-5-20251001` (피드백은 짧고 양이 많아 비용·지연이 중요. 품질 부족하면 `claude-sonnet-5`로 승급)
- `max_tokens`: 600 (피드백 4~6문장이면 충분)
- `temperature`: 0.4 (약간의 자연스러움, 사실 왜곡은 억제)
- **구조화 출력**: tool use(`emit_feedback`)로 JSON 강제 → 파싱 실패·잡담 제거
- 프롬프트 캐싱: system 프롬프트가 고정이므로 `cache_control`로 캐시(운동별 호출 반복 → 비용 절감)

## 입력 데이터 (엔진이 이미 만드는 것 — 그대로 전달)

`backend/analysis.py`의 `build()`가 내는 dict를 그대로 LLM 입력으로 넘긴다. 실제 필드:

```json
{
  "exercise_id": "squat",
  "exercise_name": "스쿼트",
  "date": "2026-08-14",
  "avg_form_score": 82,          // has_score=false면 null
  "has_score": true,
  "has_joint_data": true,        // false면 자세 미측정 → 지어내지 말 것
  "compared_with": {"date": "2026-08-12"} | null,
  "aggregate": {                 // 관절별 집계(핵심 근거) — aggregate() 결과
    "knee_angle":  {"total": 4, "bad": 0, "mean": 83.7},
    "hip_angle":   {"total": 4, "bad": 0, "mean": 99.7},
    "back_angle":  {"total": 4, "bad": 4, "mean": 83.4}
  },
  "ranges": {                    // 각 관절 목표 범위(_range) — 판단 근거
    "knee_angle": [70, 100], "hip_angle": [60, 100], "back_angle": [null, 45]
  },
  "prev_aggregate": { ... } | null,   // 이전 세션 집계(변화 서술용)
  "reps": {"total": 11, "correct": 9} // 회차 판정 요약(feedback.py)
}
```

**주의**: `aggregate`/`ranges`/`prev_aggregate`는 현재 `build()`가 내부에서만 쓰고 응답엔 안 실린다.
LLM 연동 시 `build()`가 이 원자료(raw agg)도 함께 반환하도록 **최소 확장**이 필요하다
(문장 4갈래 good/bad/change/next는 지금대로 두고, 그 근거가 된 수치를 같이 실어 LLM에 넘긴다).
그래야 LLM이 수치를 근거로 문장을 다시 쓸 수 있다. 규칙 문장은 폴백으로도 유지한다.

## System 프롬프트 (고정 — 캐시 대상)

```
당신은 홈트레이닝 앱 "The Fit"의 자세 코치입니다. 사용자가 방금 끝낸 운동의
관절 분석 결과(숫자)를 받아, 따뜻하고 구체적인 한국어 피드백으로 바꾸는 일만 합니다.

절대 규칙:
1. 당신은 영상이나 자세를 직접 보지 않았습니다. 입력으로 주어진 수치·판정만이 사실입니다.
   입력에 없는 관절, 각도, 횟수, 판정을 절대 만들어내지 마십시오. 추측 금지.
2. 모든 칭찬·지적은 입력의 수치에 근거해야 합니다. 각 문장은 어떤 관절의 어떤 수치에서
   나왔는지 스스로 답할 수 있어야 합니다.
3. has_joint_data가 false면 자세를 측정하지 못한 것입니다. 이때는 자세 얘기를 지어내지 말고,
   "이번엔 자세를 측정하지 못했다"는 사실만 부드럽게 전하고 다음 촬영을 권하십시오.
4. compared_with가 null이면 첫 기록입니다. "지난번보다" 같은 비교를 하지 마십시오.
5. 숫자를 그대로 나열하지 말고 자연스러운 문장에 녹이되, 핵심 수치(각도·범위·횟수)는
   신뢰를 위해 1~2개 남기십시오. 과장·근거 없는 단정 금지.
6. 톤: 격려하되 솔직하게. 잘한 건 인정하고, 고칠 건 부드럽지만 명확하게. 존댓말.
   운동 초보도 알아들을 쉬운 말. 전문용어는 풀어서.
7. 분량: 각 항목 1~2문장. 전체가 장황하지 않게.

의학적 조언이나 부상 진단은 하지 마십시오. 자세 코칭 범위에서만 말하십시오.
```

## User 메시지 (호출마다 — 데이터 주입)

```
아래는 방금 끝낸 {exercise_name} 세션의 관절 분석 결과입니다. 이 수치만 근거로 피드백을 만드세요.

[세션]
- 운동: {exercise_name}
- 총 반복: {reps.total}회 (그중 올바른 자세 {reps.correct}회)
- 평균 폼 점수: {avg_form_score}점   // has_score=false면 "측정 안 됨"
- 관절 데이터 있음: {has_joint_data}
- 이전 세션 비교 대상: {compared_with.date or "없음(첫 기록)"}

[관절별 집계]  (bad = 목표 범위를 벗어난 세트 수)
{각 관절: 이름 · 목표범위 [lo~hi]° · 평균 {mean}° · {total}세트 중 {bad}세트 이탈}

[이전 세션 관절 집계]  (변화 서술용, 없으면 "없음")
{prev_aggregate 동일 형식 또는 "없음"}

emit_feedback 도구로만 답하세요.
```

## 출력 스키마 (tool use — `emit_feedback`)

규칙 엔진의 4갈래 구조를 그대로 유지해 프런트가 무수정으로 받게 한다
(`app`의 요약 코치노트가 이미 good/bad/change/next/notes를 읽는다).

```json
{
  "name": "emit_feedback",
  "input_schema": {
    "type": "object",
    "properties": {
      "headline": {"type": "string", "description": "한 줄 총평 (예: '깊이는 좋았고 상체 각도만 잡으면 완성이에요')"},
      "good":   {"type": "array", "items": {"type": "string"}, "description": "잘한 점. 근거 수치 포함. 없으면 빈 배열"},
      "bad":    {"type": "array", "items": {"type": "string"}, "description": "아쉬운 점. 근거 수치 포함"},
      "change": {"type": "array", "items": {"type": "string"}, "description": "이전 대비 변화와 그 이유. 첫 기록이면 빈 배열"},
      "next":   {"type": "array", "items": {"type": "string"}, "description": "다음에 할 구체적 교정 1~2개"},
      "notes":  {"type": "array", "items": {"type": "string"}, "description": "데이터 없음 등 정직한 안내"}
    },
    "required": ["headline", "good", "bad", "change", "next", "notes"]
  }
}
```

## 안전장치 (연동 시 코드로)

- **폴백**: LLM 호출 실패·타임아웃·차단 시 → 지금의 규칙 기반 문장(`analysis.build`)을 그대로 반환.
  LLM은 "더 자연스럽게"의 옵션일 뿐, 없어도 피드백은 나온다. 이 폴백을 반드시 유지.
- **검증**: LLM 출력의 각 문장이 입력에 없는 관절명·수치를 담았는지 가벼운 후검증(관절명 화이트리스트 대조).
  벗어나면 그 항목만 버리고 규칙 문장으로 대체.
- **비용/지연**: 운동 직후 리뷰 화면은 지연에 민감 → 리뷰엔 규칙 문장(즉시), LLM은 요약 화면의
  코치노트에서 비동기로 덧입히는 것도 방법(판단은 연동 시).
- **캐싱**: system 프롬프트 `cache_control: ephemeral`. 같은 운동 반복 호출에서 입력 토큰 비용 절감.
- **키 관리**: `ANTHROPIC_API_KEY`는 `.env`로만(이미 `.gitignore`에 `.env` 처리됨). 코드·커밋에 절대 넣지 말 것.

## 연동 시 붙일 위치 (준비만, 지금은 안 붙임)

- `backend/` 신규 모듈(예 `llm_feedback.py`) — `build()` 결과 dict를 받아 Claude 호출 → 위 스키마 반환.
- `GET /sessions/{id}/analysis` 응답을 이 결과로 교체하되, **LLM 실패 시 기존 `analysis.build` 폴백**.
- `.env`에 `ANTHROPIC_API_KEY`, 선택적 `LLM_FEEDBACK=on|off`(끄면 규칙 기반) 스위치.
- 의존성: `anthropic` (파이썬 SDK) — 연동 시 `requirements.txt`에 추가.

## 왜 지금은 안 붙이나

- API 키·비용·지연·검증 파이프라인이 필요해 "미리 준비"만 해둔다.
- 규칙 기반이 이미 정확히 동작하므로 서비스는 그걸로 성립한다. LLM은 문장 품질 업그레이드다.
- 붙일 준비가 되면 이 문서의 프롬프트·스키마를 그대로 코드로 옮기면 된다.

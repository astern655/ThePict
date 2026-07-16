# 프로젝트 작업 규칙

## 역할

- Claude Code는 요구사항 정리, 구현 계획, 코드 수정, 테스트, 최종 보고를 주로 담당한다.
- Codex CLI는 독립적인 계획 검토, 실패 분석, Git diff 리뷰를 주로 담당한다.
- Codex의 제안은 참고 자료다. Claude는 프로젝트 규칙과 실제 테스트 결과를 우선한다.

## Codex 위임 규칙

다음 상황에서는 `.claude/scripts/codex-consult.ps1`을 읽기 전용으로 실행하고 결과를 검토한다.

```powershell
powershell -File .claude/scripts/codex-consult.ps1 <mode> "<task statement>"
```

1. 다단계 구현 계획 또는 여러 파일/API/데이터 모델/의존성 변경 전: `plan-review`
2. 한 번 수정한 뒤에도 테스트가 실패하거나 원인이 불명확할 때: `failure-analysis`
3. 구현·테스트가 완료되어 Git diff 검토가 필요할 때: `final-review`

다음 상황에서는 Codex를 호출하지 않는다.

- 오타·문구·명확한 단일 파일의 작은 수정
- 표준 Git 상태 확인과 단순 테스트 실행
- 이미 검증된 반복 작업

## 작업 순서

1. 관련 코드와 프로젝트 문서를 탐색한다.
2. 필요할 때만 Codex 계획 검토를 실행한다.
3. Claude가 구현하고 관련 테스트를 실행한다.
4. 실패가 불명확하면 Codex 실패 분석을 한 번 실행한다.
5. 완료 전 Codex 최종 리뷰를 실행하고, 필요한 수정과 테스트를 Claude가 수행한다.
6. 최종 결과에는 변경점, 실행한 검증, 남은 위험을 짧게 보고한다.

## 안전성

- Codex는 항상 `--sandbox read-only`로 실행한다.
- 비밀값, 개인 정보, `.env` 내용, 운영 데이터는 어떤 상담 프롬프트에도 넣지 않는다.
- `--dangerously-bypass-approvals-and-sandbox`를 사용하지 않는다.   

## 프로젝트별 정보

프로젝트 시작 시 아래를 실제 값으로 교체한다.

- 목적:
- 개발 명령:
- 테스트 명령:
- 린트/형식 명령:
- 핵심 디렉터리:
- 완료 기준:

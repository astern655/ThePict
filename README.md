# Claude Max + Codex 협업 템플릿

Claude Code가 작업을 지휘하고, Codex CLI가 읽기 전용으로 계획 검토·실패 분석·최종 리뷰를 수행하는 개인용 Git 프로젝트 템플릿입니다.

## 시작하기

1. 이 폴더를 새 Git 프로젝트의 루트로 복사합니다.
2. WSL Ubuntu에서 해당 Windows 경로로 이동합니다. 예: `cd /mnt/c/Users/<WindowsUser>/Documents/my-project`
3. 최초 한 번 `.claude/scripts/bootstrap-wsl.sh`를 실행합니다. Node.js와 두 CLI를 WSL 사용자 홈에 설치합니다.
4. 새 WSL 터미널에서 `claude`를 실행해 Claude Max 계정으로 로그인합니다.
5. `codex login`을 실행해 Codex 계정으로 로그인합니다.
6. Claude에게 작업을 요청합니다. 다단계 계획, 불명확한 실패, 구현 완료 후 검토가 필요하면 Claude가 `codex-consult.sh`를 사용합니다.
7.AI가 수행하는 작업은 구현은 AI가 하되 사용자 과정을 이해하고 공부하는것이 가장 주된 목적임 이를 고려해서 출력 

## 협업 방식

| 단계 | 담당 | Codex 사용 |
| --- | --- | --- |
| 요구사항 정리·구현 계획 | Claude | 여러 파일/API/DB/의존성 변경이면 계획 검토 |
| 구현·테스트 | Claude | 사용하지 않음 |
| 반복 실패·원인 불명 | Claude + Codex | 실패 분석 |
| 완료 확인 | Claude + Codex | Git diff 최종 리뷰 |

Codex는 기본적으로 `read-only` 샌드박스로만 실행됩니다. Codex가 제안한 수정은 Claude가 테스트 결과와 프로젝트 규칙을 기준으로 선택합니다.

## Codex 상담 명령

WSL Bash에서 프로젝트 루트에서 실행합니다.

```bash
.claude/scripts/codex-consult.sh plan-review "<검토할 구현 계획>"
.claude/scripts/codex-consult.sh failure-analysis "<실패 상황과 재현 방법>"
.claude/scripts/codex-consult.sh final-review "<완료한 작업의 목표와 검증 결과>"
```

상담 결과는 `.claude/docs/codex-reviews/`에 저장되며 Git에서는 제외됩니다. 확정된 설계 결정만 사람이 검토한 뒤 `docs/` 또는 `CLAUDE.md`에 요약합니다.

## 보안

- API 키, `.env`, 개인정보, 운영 데이터, 원문 비밀 로그를 프롬프트나 보고서에 넣지 않습니다.
- `--dangerously-bypass-approvals-and-sandbox`는 사용하지 않습니다.
- Codex에 쓰기 작업을 위임하려면 별도 브랜치와 명시적 사용자 승인을 사용하는 v2 흐름을 만듭니다.

# Claude Max 작업 템플릿

Claude Code가 요구사항 정리·구현·테스트·보고를 담당하는 개인용 Git 프로젝트 템플릿입니다.

## 시작하기

1. 이 폴더를 새 Git 프로젝트의 루트로 복사합니다.
2. WSL Ubuntu에서 해당 Windows 경로로 이동합니다. 예: `cd /mnt/c/Users/<WindowsUser>/Documents/my-project`
3. 최초 한 번 `.claude/scripts/bootstrap-wsl.sh`를 실행합니다. Node.js와 CLI를 WSL 사용자 홈에 설치합니다.
4. 새 WSL 터미널에서 `claude`를 실행해 Claude Max 계정으로 로그인합니다.
5. Claude에게 작업을 요청합니다.
6. AI가 수행하는 작업은 구현은 AI가 하되 사용자가 과정을 이해하고 공부하는 것이 가장 주된 목적임. 이를 고려해서 출력.

## 작업 방식

| 단계 | 담당 |
| --- | --- |
| 요구사항 정리·구현 계획 | Claude |
| 구현·테스트 | Claude |
| 완료 확인 | Claude |

확정된 설계 결정만 사람이 검토한 뒤 `docs/` 또는 `CLAUDE.md`에 요약합니다.

## 보안

- API 키, `.env`, 개인정보, 운영 데이터, 원문 비밀 로그를 프롬프트나 보고서에 넣지 않습니다.

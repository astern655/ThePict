"""AI 엔진 패키지.

서버·프론트엔드를 전혀 모르는 독립 모듈이다.
바깥(백엔드 Worker·CLI 등)은 이 `ai` 파사드만 보면 되도록,
연결에 필요한 것들을 여기서 한곳에 노출한다.

- analyze_video       : 유일한 실행 진입점 (영상 경로 → Report)
- Report              : 반환·JSON 직렬화(to_dict) 타입
- available_exercises : 지원 운동 목록 (예: GET /exercises)
- PoseDetector        : 모델을 1회 로드해 재사용하려는 Worker가 주입용으로 생성
"""
from ai.analysis.exercises import available_exercises
from ai.analysis.feedback import Report
from ai.engine import analyze_video
from ai.pose.detector import PoseDetector

__all__ = ["analyze_video", "Report", "available_exercises", "PoseDetector"]

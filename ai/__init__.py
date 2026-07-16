"""AI 엔진 패키지.

서버·프론트엔드를 전혀 모르는 독립 모듈이다.
바깥에서 쓰는 공개 진입점은 engine.analyze_video 하나뿐.
"""
from ai.engine import analyze_video

__all__ = ["analyze_video"]

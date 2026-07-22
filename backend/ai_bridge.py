"""로컬 AI 엔진(저장소 루트의 `ai/` 패키지)을 백엔드에 연결하는 다리.

백엔드는 `backend/` 를 작업 디렉터리로 띄우므로(`uvicorn main:app`) 저장소 루트가
sys.path에 없다. 여기서 한 번만 넣어 두면 backend 어디에서나 `import ai` 가 된다.

무거운 ML 런타임(torch/ultralytics/opencv)은 실제로 쓰는 순간까지 import 하지
않는다. 그래야 AI 의존성을 깔지 않은 환경에서도 인증·세션·프로그램 API가 뜬다.
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


class EngineUnavailable(RuntimeError):
    """AI 엔진을 import 할 수 없다(의존성 미설치 등). 호출부가 503으로 바꾼다."""


def ensure_path() -> None:
    """저장소 루트를 sys.path에 넣어 `import ai` 가 되게 한다. 여러 번 불러도 안전."""
    root = str(PROJECT_ROOT)
    if root not in sys.path:
        sys.path.insert(0, root)


def load_config():
    """`ai.config` 모듈. 임계값만 들어 있어 ML 런타임 없이도 import 된다."""
    ensure_path()
    try:
        import ai.config as config
    except ImportError as exc:  # pragma: no cover - 패키지 자체가 없는 비정상 배치
        raise EngineUnavailable(f"ai 패키지를 찾을 수 없습니다: {exc}") from exc
    return config


def load_engine():
    """`ai.engine` 모듈. opencv/ultralytics가 필요하다."""
    ensure_path()
    try:
        import ai.engine as engine
    except ImportError as exc:
        raise EngineUnavailable(
            "AI 엔진 의존성이 설치되지 않았습니다. "
            "저장소 루트에서 `pip install -r requirements.txt` 를 실행하세요. "
            f"(원인: {exc})"
        ) from exc
    return engine


def load_detector_class():
    """`ai.pose.detector.PoseDetector` 클래스. ultralytics가 필요하다."""
    ensure_path()
    try:
        from ai.pose.detector import PoseDetector
    except ImportError as exc:
        raise EngineUnavailable(
            "YOLO Pose 런타임이 설치되지 않았습니다. "
            "저장소 루트에서 `pip install -r requirements.txt` 를 실행하세요. "
            f"(원인: {exc})"
        ) from exc
    return PoseDetector

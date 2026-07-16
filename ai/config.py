"""AI 엔진 설정.

임계값·경로 같은 '숫자와 문자열'을 코드 곳곳에 흩뿌리지 않고 여기에 모은다.
튜닝할 때 이 파일만 보면 되도록 하는 것이 목적.
"""
from __future__ import annotations

from pathlib import Path

# --- 경로 ---------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
MODELS_DIR = PROJECT_ROOT / "models"
DATA_DIR = PROJECT_ROOT / "data"
OUTPUT_DIR = DATA_DIR / "output"

for _d in (MODELS_DIR, DATA_DIR, OUTPUT_DIR):
    _d.mkdir(parents=True, exist_ok=True)

# --- 모델 ---------------------------------------------------------------
# n(nano) < s < m < l < x 순으로 무겁고 정확해짐. 처음엔 가벼운 n으로.
# 파일이 없으면 ultralytics가 최초 실행 시 자동 다운로드한다.
POSE_MODEL = "yolo11n-pose.pt"

# 관절 신뢰도가 이 값보다 낮으면 '못 본 것'으로 간주하고 계산에서 제외.
MIN_KEYPOINT_CONFIDENCE = 0.5

# --- 스쿼트 반복 카운트 임계값 (도) --------------------------------------
# 히스테리시스: 내려감/올라옴 판정에 서로 다른 각을 써서 경계 떨림을 막는다.
SQUAT_KNEE_DOWN_ANGLE = 100.0   # 이보다 작아지면 '앉음(DOWN)'
SQUAT_KNEE_UP_ANGLE = 160.0     # 이보다 커지면 '일어섬(UP)'

# --- 스쿼트 자세 규칙 임계값 (측면 촬영 전용) ---------------------------
# 스쿼트 영상은 측면 촬영만 받는다(근거: docs/CAPTURE_AND_SQUAT_CRITERIA.md).
# 측면에서 정확히 측정 가능한 깊이·상체 앞숙임만 평가하며, 두 규칙 모두
# rep 최저점(가장 깊이 앉은 프레임)의 관절을 기준으로 판정한다.
SQUAT_GOOD_DEPTH_ANGLE = 100.0    # 최저점 무릎각이 이보다 크면 '깊이 부족'
SQUAT_TORSO_LEAN_MAX = 45.0       # 몸통 기울기(도)가 이보다 크면 '과도한 앞숙임'

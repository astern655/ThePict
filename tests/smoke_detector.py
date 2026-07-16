"""YOLO 연동 스모크 테스트.

실제 사람 영상 없이, 모델이 로드되고 추론이 크래시 없이 도는지만 확인한다.
(최초 실행 시 yolo11n-pose.pt 자동 다운로드 → 인터넷 필요)
실행: py -m tests.smoke_detector
"""
from __future__ import annotations

import numpy as np

from ai.pose.detector import PoseDetector


def main() -> None:
    print("모델 로딩 중... (최초엔 다운로드로 시간이 걸릴 수 있음)")
    det = PoseDetector()
    print("✅ 모델 로드 성공")

    # 640x480 검은 이미지 → 사람 없음 → None 이어야 함
    blank = np.zeros((480, 640, 3), dtype=np.uint8)
    result = det.detect(blank)
    print(f"✅ 빈 프레임 추론 성공 (검출 결과: {result})")
    assert result is None, "빈 화면에서 사람이 검출되면 안 됨"
    print("\nYOLO 연동 정상 🎉")


if __name__ == "__main__":
    main()

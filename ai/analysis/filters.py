"""시계열 평활화 필터.

관절 검출 좌표는 프레임마다 미세하게 떨린다. 각도 시계열을 그대로 쓰면
임계값 경계에서 rep이 이중 카운트되거나 최저점이 튄 프레임으로 잡힌다.
중앙값 필터는 단발 스파이크를 제거하면서도 (이동평균과 달리) 실제
내려가는/올라오는 흐름의 값을 뭉개지 않는다.
"""
from __future__ import annotations

import statistics
from collections import deque


class MedianSmoother:
    """최근 window개 표본의 중앙값을 돌려주는 스트리밍 필터.

    window=1이면 입력을 그대로 통과시킨다(비활성).
    """

    def __init__(self, window: int) -> None:
        self._buffer: deque[float] = deque(maxlen=max(1, window))

    def push(self, value: float) -> float:
        """표본 하나를 넣고 현재 평활값을 반환."""
        self._buffer.append(value)
        return statistics.median(self._buffer)

    def reset(self) -> None:
        self._buffer.clear()

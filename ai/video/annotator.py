"""프레임 위에 관절과 뼈대를 그려주는 유틸.

분석 결과를 눈으로 확인할 수 있는 '주석 영상'을 만들 때 쓴다.
순수하게 그림만 담당 — 분석 로직은 모른다.
"""
from __future__ import annotations

import cv2
import numpy as np

from ai.pose.detector import Person
from ai.pose.keypoints import SKELETON

_JOINT_COLOR = (0, 255, 0)     # 초록 점
_BONE_COLOR = (255, 180, 0)    # 파란 선 (BGR)
_TEXT_COLOR = (255, 255, 255)


def draw_person(
    frame: np.ndarray, person: Person, bone_color: tuple[int, int, int] | None = None
) -> np.ndarray:
    """관절 점 + 뼈대 선을 프레임에 그려 새 이미지를 반환.

    bone_color를 주면 뼈대 색을 바꾼다(예: 직전 rep 판정색 초록/노랑/빨강).
    """
    out = frame.copy()

    # 뼈대(선) 먼저
    for a, b in SKELETON:
        if person[a].visible and person[b].visible:
            pa = (int(person[a].x), int(person[a].y))
            pb = (int(person[b].x), int(person[b].y))
            cv2.line(out, pa, pb, bone_color or _BONE_COLOR, 2)

    # 관절(점)
    for kp in person:
        if kp.visible:
            cv2.circle(out, (int(kp.x), int(kp.y)), 4, _JOINT_COLOR, -1)

    return out


def draw_hud(frame: np.ndarray, lines: list[str]) -> np.ndarray:
    """좌상단에 반투명 배경 + 텍스트(반복 수 등)를 얹는다."""
    out = frame
    y = 30
    for line in lines:
        cv2.putText(out, line, (12, y), cv2.FONT_HERSHEY_SIMPLEX,
                    0.8, (0, 0, 0), 4, cv2.LINE_AA)   # 검은 외곽선
        cv2.putText(out, line, (12, y), cv2.FONT_HERSHEY_SIMPLEX,
                    0.8, _TEXT_COLOR, 2, cv2.LINE_AA)  # 흰 글씨
        y += 34
    return out

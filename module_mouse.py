"""Mouse automation helpers for NoClic."""

from __future__ import annotations

import math
from typing import Iterable, Tuple

import pyautogui

Point = Tuple[int, int]


def calculate_manhattan_distance(point_a: Point, point_b: Point) -> int:
    """Return the Manhattan distance between two pixel coordinates."""
    return abs(point_a[0] - point_b[0]) + abs(point_a[1] - point_b[1])


def is_within_deadzone(position: Point, anchor_position: Point | None, radius: float) -> bool:
    """Determine whether a position stays inside the configured deadzone."""
    if anchor_position is None:
        return False
    return math.hypot(position[0] - anchor_position[0], position[1] - anchor_position[1]) < radius


def release_mouse_button_safely(button: str = "left") -> None:
    """Force a mouse-up event without moving the cursor."""
    try:
        x_pos, y_pos = pyautogui.position()
        pyautogui.mouseUp(x_pos, y_pos, button=button)
    except Exception:
        pass

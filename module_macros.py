"""Utility macros for keyboard-driven automation actions."""

from __future__ import annotations

import sys
import time
from typing import Final

import pyautogui

CTRL_KEY: Final[str] = "command" if sys.platform == "darwin" else "ctrl"


def copy_selection_to_clipboard() -> None:
    """Copy the current selection to the clipboard."""
    pyautogui.hotkey(CTRL_KEY, "c")


def select_all_text() -> None:
    """Select all text in the focused control."""
    pyautogui.hotkey(CTRL_KEY, "a")


def paste_clipboard_content() -> None:
    """Paste clipboard content into the focused control."""
    pyautogui.hotkey(CTRL_KEY, "v")


def copy_entire_document() -> None:
    """Copy the entire document by selecting all then copying."""
    select_all_text()
    time.sleep(0.02)
    copy_selection_to_clipboard()


def delete_and_backspace() -> None:
    """Send delete followed by backspace to clear focused content."""
    try:
        pyautogui.press("delete")
    except Exception:
        pass
    time.sleep(0.02)
    try:
        pyautogui.press("backspace")
    except Exception:
        pass


def select_and_copy_current() -> None:
    """Select all text and copy it to the clipboard (SELCP macro)."""
    select_all_text()
    time.sleep(0.05)
    copy_selection_to_clipboard()

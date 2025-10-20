# utils.py — utilitaires communs (mouvement, clavier, sécurité)
import math
import sys
import time
import pyautogui
from pathlib import Path

def manhattan(p1, p2):
    return abs(p1[0]-p2[0]) + abs(p1[1]-p2[1])

def kb_copy():
    pyautogui.hotkey("command" if sys.platform=="darwin" else "ctrl", "c")

def kb_select_all():
    pyautogui.hotkey("command" if sys.platform=="darwin" else "ctrl", "a")

def kb_paste():
    pyautogui.hotkey("command" if sys.platform=="darwin" else "ctrl", "v")

def kb_copy_all():
    """Sélectionne tout puis copie."""
    kb_select_all()
    time.sleep(0.02)
    kb_copy()

def delete_or_backspace():
    try: pyautogui.press("delete")
    except: pass
    time.sleep(0.02)
    try: pyautogui.press("backspace")
    except: pass

def safe_mouseup():
    try:
        x, y = pyautogui.position()
        pyautogui.mouseUp(x, y, button="left")
    except:
        pass

def inside_deadzone(pos, anchor_point, radius):
    return (anchor_point is not None) and (
        math.hypot(pos[0]-anchor_point[0], pos[1]-anchor_point[1]) < radius
    )


def user_data_path(filename: str) -> Path:
    """
    Retourne un chemin persistant pour les données utilisateur.
    - Windows : %APPDATA%/NoClicApp/settings.json
    - Linux/macOS : ~/.config/NoClicApp/settings.json
    """
    import os
    import sys
    from pathlib import Path

    if getattr(sys, 'frozen', False):  # App compilée
        if os.name == 'nt':  # Windows
            base = Path(os.getenv('APPDATA')) / "NoClicApp"
        else:  # Linux / macOS
            base = Path.home() / ".config" / "NoClicApp"
    else:  # En développement
        base = Path(__file__).parent

    base.mkdir(parents=True, exist_ok=True)
    return base / filename
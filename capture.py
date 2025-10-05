# capture.py — capture rectangulaire -> presse-papiers (CF_DIB)
from PIL import ImageGrab
import sys
from clipboard_win import copy_image_to_clipboard_win

def screenshot_to_clipboard(x1, y1, x2, y2):
    L, T, R, B = min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2)
    if R - L < 2 or B - T < 2:
        return False, "SHOT: zone trop petite"

    img = ImageGrab.grab(bbox=(L, T, R, B))
    if sys.platform.startswith("win"):
        ok = copy_image_to_clipboard_win(img, force_clear=True)
        return ok, ("📸 Copié dans le presse-papiers" if ok else "❌ Clipboard occupé — réessaie")
    else:
        return False, "📸 Copie directe du clipboard non supportée hors Windows"

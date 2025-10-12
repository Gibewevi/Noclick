# capture.py — capture rectangulaire -> presse-papiers (CF_DIB)
from PIL import ImageGrab
import sys

try:
    import pyautogui
except Exception:
    pyautogui = None

from clipboard_win import copy_image_to_clipboard_win


def _looks_mostly_black(img):
    """Heuristic: detect the fully black captures returned by some GPU apps."""
    try:
        gray = img.convert("L")
        hist = gray.histogram()
        total = sum(hist)
        if not total:
            return False
        # Average brightness (0..255)
        avg = sum(idx * count for idx, count in enumerate(hist)) / float(total)
        black_ratio = hist[0] / float(total)
        return avg < 3 and black_ratio > 0.96
    except Exception:
        return False


def _grab_with_pillow(bbox, include_layered):
    kwargs = {"bbox": bbox}
    if include_layered is not None:
        kwargs["include_layered_windows"] = include_layered
    return ImageGrab.grab(**kwargs)


def _grab_region(bbox):
    # Try Pillow with layered windows first (better for GPU-accelerated apps)
    attempts = (True, None)
    last_exc = None
    for layered in attempts:
        try:
            img = _grab_with_pillow(bbox, layered)
            if not _looks_mostly_black(img):
                return img
        except TypeError:
            # Older Pillow: include_layered_windows not supported
            continue
        except OSError as exc:
            last_exc = exc
            continue
    # Fallback to pyautogui (uses its own DPI handling / capture path)
    if pyautogui is not None:
        try:
            left, top, right, bottom = bbox
            width = max(1, right - left)
            height = max(1, bottom - top)
            img = pyautogui.screenshot(region=(left, top, width, height))
            return img
        except Exception as exc:
            last_exc = exc
    if last_exc:
        raise last_exc
    raise RuntimeError("screenshot failed")


def screenshot_to_clipboard(x1, y1, x2, y2):
    L, T, R, B = min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2)
    if R - L < 2 or B - T < 2:
        return False, "SHOT: zone trop petite"

    bbox = (L, T, R, B)
    try:
        img = _grab_region(bbox)
    except Exception as exc:
        return False, f"SHOT: capture impossible ({exc})"

    # If final image is still black (protected content), warn the user.
    if _looks_mostly_black(img):
        return False, "SHOT: contenu protégé ou impossible à capturer (surface noire)"

    if sys.platform.startswith("win"):
        ok = copy_image_to_clipboard_win(img, force_clear=True)
        return ok, ("📸 Copié dans le presse-papiers" if ok else "❌ Clipboard occupé — réessaie")
    else:
        return False, "📸 Copie directe du clipboard non supportée hors Windows"

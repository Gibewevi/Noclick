# clipboard_win.py — copie d’image en CF_DIB (Windows) avec vidage + retries
from PIL import Image
import time
from config import CLIP_OPEN_RETRIES, CLIP_VERIFY_TRIES

def copy_image_to_clipboard_win(img: Image.Image,
                                force_clear: bool = True,
                                open_retries: int = CLIP_OPEN_RETRIES,
                                verify_retries: int = CLIP_VERIFY_TRIES) -> bool:
    """
    Copie l'image dans le presse-papiers Windows en CF_DIB (bitmap).
    - Vide le clipboard avant (EmptyClipboard) si force_clear=True.
    - Réessaie si OpenClipboard échoue (clipboard occupé).
    - Vérifie la présence du format CF_DIB après.
    """
    try:
        import win32clipboard as wcb, win32con, io
    except Exception as e:
        print("pywin32 manquant ?", e)
        return False

    # Convertit en BMP et retire l'entête 14 octets -> CF_DIB
    with io.BytesIO() as output:
        bmp = img.convert("RGB")
        bmp.save(output, "BMP")
        dib = output.getvalue()[14:]

    # Ouvrir/vider/écrire avec retries
    for i in range(open_retries):
        try:
            wcb.OpenClipboard()
            try:
                if force_clear:
                    wcb.EmptyClipboard()
                    time.sleep(0.01)
                wcb.SetClipboardData(win32con.CF_DIB, dib)
            finally:
                wcb.CloseClipboard()
            break
        except Exception:
            time.sleep(0.04 + i * 0.01)
    else:
        return False

    # Vérification CF_DIB disponible
    for _ in range(verify_retries):
        try:
            wcb.OpenClipboard()
            try:
                if wcb.IsClipboardFormatAvailable(win32con.CF_DIB):
                    return True
            finally:
                wcb.CloseClipboard()
        except Exception:
            pass
        time.sleep(0.05)
    return False

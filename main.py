# main.py — NOCLIC HUD (CF_DIB simple, vidage clipboard, retries légers)
# ---------------------------------------------------------------------
# CLICK : clic par immobilité (deadzone + réarmement)
# SEL   : immobilité 1 = mouseDown ; immobilité 2 = mouseUp + Copie
# SHOT  : immobilité 1 = lock ; immobilité 2 = capture -> Presse-papiers (CF_DIB)
# COL   : armement, focus, Ctrl/Cmd+A -> Delete/Backspace -> Ctrl/Cmd+V (+ timeout)
# ---------------------------------------------------------------------

import customtkinter as ctk
import pyautogui
import time
import threading
import math
import sys
import os
from datetime import datetime
from PIL import ImageGrab, Image

# ================== PARAMÈTRES VISUELS ==================
HUD_W            = 280
HUD_H            = 120
HUD_MARGIN       = 12
HUD_CORNER       = 8

BTN_W            = 60
BTN_H            = 28
BTN_CORNER       = 6
BTN_FONT         = ("Consolas", 11)

CLOSE_BTN_W      = 24
CLOSE_BTN_H      = 22
CLOSE_BTN_CORNER = 6

HEADER_PADY      = (4, 0)
ROW_PADY         = (10, 0)
HINT_PADY        = (2, 0)
BAR_PADY         = (2, 6)

BAR_HEIGHT       = 8
BAR_CORNER       = 4
BAR_DEFAULT      = "#1f6aa5"
BAR_WARN         = "#f39c12"
BAR_OK           = "#27ae60"
BAR_ARM          = "#7f8c8d"
# ========================================================

# ================== PARAMÈTRES LOGIQUES ==================
USE_OS_SNIPPER    = False      # True => Win+Shift+S (copie gérée par l'OS)
SHOT_ARM_SECONDS  = 2.0
SEL_ARM_SECONDS   = 1.0
COL_ARM_SECONDS   = 0.8
COL_TIMEOUT_SECS  = 5.0
DWELL_DELAY_INIT  = 0.7
DEADZONE_RADIUS   = 28
MOVE_EPS          = 2
# Retries clipboard (simples, rapides)
CLIP_OPEN_RETRIES = 40
CLIP_VERIFY_TRIES = 20
# ========================================================

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

# ---------------- État ----------------
running               = True
dwell_delay           = DWELL_DELAY_INIT
progress_value        = 0.0

selection_mode        = False
selection_phase_down  = False
selection_arm_until   = 0.0

screenshot_mode       = False
screenshot_phase_down = False
screenshot_arm_until  = 0.0
shot_anchor           = None

col_mode              = False
col_arm_until         = 0.0
col_started_at        = 0.0

anchor_point          = None
rearm_in_deadzone     = False

# ------------ Utilitaires -------------
def manhattan(p1, p2): return abs(p1[0]-p2[0]) + abs(p1[1]-p2[1])

def inside_deadzone(pos):
    return (anchor_point is not None) and (math.hypot(pos[0]-anchor_point[0], pos[1]-anchor_point[1]) < DEADZONE_RADIUS)

def do_left_click_at(pos):
    global anchor_point
    pyautogui.click(pos[0], pos[1]); anchor_point = pos

def kb_copy():        pyautogui.hotkey("command" if sys.platform=="darwin" else "ctrl", "c")
def kb_select_all():  pyautogui.hotkey("command" if sys.platform=="darwin" else "ctrl", "a")
def kb_paste():       pyautogui.hotkey("command" if sys.platform=="darwin" else "ctrl", "v")

def delete_or_backspace():
    try: pyautogui.press("delete")
    except: pass
    time.sleep(0.02)
    try: pyautogui.press("backspace")
    except: pass

def safe_mouseup():
    try:
        x,y=pyautogui.position(); pyautogui.mouseUp(x,y,button="left")
    except: pass

# ----- CLIPBOARD IMAGE (Windows) : CF_DIB simple + EmptyClipboard + retries -----
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

    # CF_DIB = BMP sans les 14 octets d'entête
    with io.BytesIO() as output:
        bmp = img.convert("RGB")
        bmp.save(output, "BMP")
        dib = output.getvalue()[14:]

    # Tente d'ouvrir, vider, puis pousser CF_DIB (retries légers)
    for i in range(open_retries):
        try:
            wcb.OpenClipboard()
            try:
                if force_clear:
                    wcb.EmptyClipboard()
                    time.sleep(0.01)  # petit délai après vidage
                wcb.SetClipboardData(win32con.CF_DIB, dib)
            finally:
                wcb.CloseClipboard()
            break
        except Exception:
            time.sleep(0.04 + i * 0.01)
    else:
        return False

    # Vérifie que CF_DIB est présent
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

def screenshot_internal(x1, y1, x2, y2):
    L, T, R, B = min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2)
    if R - L < 2 or B - T < 2:
        hint.configure(text="SHOT: zone trop petite")
        return
    img = ImageGrab.grab(bbox=(L, T, R, B))
    if sys.platform.startswith("win"):
        ok = copy_image_to_clipboard_win(img, force_clear=True)
        hint.configure(text=("📸 Copié dans le presse-papiers" if ok else "❌ Clipboard occupé — réessaie"))
    else:
        hint.configure(text="📸 Copie directe du clipboard non supportée hors Windows")

# ============== Boucle Dwell ==============
def dwell_loop():
    global anchor_point,rearm_in_deadzone
    global selection_mode,selection_phase_down,selection_arm_until
    global screenshot_mode,screenshot_phase_down,screenshot_arm_until,shot_anchor
    global col_mode, col_arm_until, col_started_at
    global progress_value

    prev=pyautogui.position(); t0=time.time()
    while True:
        pos=pyautogui.position(); moved=manhattan(pos,prev)>MOVE_EPS
        if running:
            if moved:
                if anchor_point and not inside_deadzone(pos): rearm_in_deadzone=True
                prev=pos; t0=time.time(); progress_value=0.0
            else:
                now=time.time(); elapsed=now-t0
                progress_value=max(0.0,min(elapsed/dwell_delay,1.0))

                if elapsed>=dwell_delay:
                    # --- COL ---
                    if col_mode:
                        if now - col_started_at > COL_TIMEOUT_SECS:
                            col_mode=False
                            hint.configure(text="COL: annulé (timeout)")
                            bar.configure(progress_color=BAR_DEFAULT)
                            refresh_status()
                            t0=now; progress_value=0.0
                        elif now < col_arm_until:
                            t0=now; progress_value=0.0
                        else:
                            try:
                                pyautogui.click(pos[0], pos[1])  # focus
                                time.sleep(0.08)
                                kb_select_all(); time.sleep(0.02)
                                delete_or_backspace(); time.sleep(0.02)
                                kb_paste()
                                hint.configure(text="COL: collé ✓")
                            except Exception as e:
                                hint.configure(text=f"COL: erreur ({e})")
                            finally:
                                col_mode=False
                                bar.configure(progress_color=BAR_DEFAULT)
                                refresh_status()
                                t0=now; progress_value=0.0

                    # --- SEL ---
                    elif selection_mode:
                        if not selection_phase_down:
                            if now<selection_arm_until:
                                t0=now; progress_value=0.0
                            else:
                                pyautogui.mouseDown(pos[0],pos[1],button="left")
                                selection_phase_down=True
                                hint.configure(text="SEL: lock ✓ → déplacez puis immobilisez pour valider")
                                bar.configure(progress_color=BAR_OK)
                                t0=now; progress_value=0.0
                        else:
                            pyautogui.mouseUp(pos[0],pos[1],button="left"); kb_copy()
                            selection_mode=False; selection_phase_down=False
                            hint.configure(text=""); bar.configure(progress_color=BAR_DEFAULT)
                            refresh_status(); t0=now; progress_value=0.0

                    # --- SHOT ---
                    elif screenshot_mode:
                        if USE_OS_SNIPPER and sys.platform.startswith("win") and not screenshot_phase_down:
                            pyautogui.hotkey("win","shift","s")
                            screenshot_mode=False
                            hint.configure(text="SHOT: utilisez l’outil OS, puis Ctrl+V")
                            bar.configure(progress_color=BAR_DEFAULT)
                            refresh_status()
                            t0=now; progress_value=0.0
                        elif not screenshot_phase_down:
                            if now<screenshot_arm_until:
                                t0=now; progress_value=0.0
                            else:
                                shot_anchor=(pos[0],pos[1])
                                screenshot_phase_down=True
                                hint.configure(text="SHOT: lock ✓ → déplacez puis immobilisez pour valider")
                                bar.configure(progress_color=BAR_OK)
                                t0=now; progress_value=0.0
                        else:
                            x1,y1=shot_anchor; x2,y2=pos[0],pos[1]
                            screenshot_internal(x1,y1,x2,y2)
                            screenshot_mode=False; screenshot_phase_down=False; shot_anchor=None
                            bar.configure(progress_color=BAR_DEFAULT)
                            refresh_status(); t0=now; progress_value=0.0

                    # --- CLICK ---
                    else:
                        if (anchor_point is None) or (not inside_deadzone(pos)) or rearm_in_deadzone:
                            do_left_click_at(pos); rearm_in_deadzone=False
                        t0=now; progress_value=0.0
        else:
            progress_value=0.0; time.sleep(0.05)

        time.sleep(0.05)

# ============== HUD ==============
def make_dwell_button(parent,label,command):
    btn=ctk.CTkButton(parent,text=label,width=BTN_W,height=BTN_H,
                      corner_radius=BTN_CORNER,font=BTN_FONT)
    btn._after=None
    def on_enter(_): btn._after=root.after(550,command)  # dwell HUD
    def on_leave(_):
        if btn._after: root.after_cancel(btn._after); btn._after=None
    btn.bind("<Enter>",on_enter); btn.bind("<Leave>",on_leave)
    btn.pack(side="left",padx=4,pady=0); return btn

def refresh_status():
    status_lbl.configure(text="ON" if running else "OFF")
    dot_lbl.configure(text_color="#2ecc71" if running else "#e74c3c")
    if col_mode:          mode="COL"
    elif selection_mode:  mode="SEL"
    elif screenshot_mode: mode="SHOT"
    else:                 mode="CLICK"
    info_lbl.configure(text=f"• {dwell_delay:.1f}s • {DEADZONE_RADIUS}px • {mode}")

def set_running(v): 
    global running; running=v; refresh_status()
def toggle_running(): set_running(not running)

def toggle_selection():
    global selection_mode,selection_phase_down,selection_arm_until,col_mode
    reset_shot(); col_mode=False
    selection_mode=not selection_mode; selection_phase_down=False
    selection_arm_until=time.time()+SEL_ARM_SECONDS if selection_mode else 0.0
    if selection_mode:
        hint.configure(text=f"SEL: prêt dans {SEL_ARM_SECONDS:.1f}s — placez-vous")
        bar.configure(progress_color=BAR_ARM)
    else:
        hint.configure(text=""); bar.configure(progress_color=BAR_DEFAULT)
    refresh_status()

def reset_shot():
    global screenshot_mode,screenshot_phase_down,shot_anchor
    screenshot_mode=False; screenshot_phase_down=False; shot_anchor=None
    hint.configure(text=""); bar.configure(progress_color=BAR_DEFAULT)

def start_shot():
    global screenshot_mode,screenshot_phase_down,screenshot_arm_until,shot_anchor,col_mode
    toggle_selection() if selection_mode else None
    col_mode=False
    screenshot_mode=True; screenshot_phase_down=False; shot_anchor=None
    screenshot_arm_until=time.time()+SHOT_ARM_SECONDS
    hint.configure(text=f"SHOT: prêt dans {SHOT_ARM_SECONDS:.1f}s — placez-vous")
    bar.configure(progress_color=BAR_ARM)
    refresh_status()

def start_col():
    global col_mode, col_arm_until, col_started_at, selection_mode, screenshot_mode
    selection_mode=False; screenshot_mode=False
    col_mode=True
    col_started_at = time.time()
    col_arm_until  = col_started_at + COL_ARM_SECONDS
    hint.configure(text=f"COL: prêt dans {COL_ARM_SECONDS:.1f}s — placez-vous")
    bar.configure(progress_color=BAR_ARM)
    refresh_status()

def update_progress():
    now=time.time()
    if selection_mode and not selection_phase_down and now<selection_arm_until:
        rest=max(0.0,selection_arm_until-now)
        hint.configure(text=f"SEL: prêt dans {rest:.1f}s — placez-vous"); bar.configure(progress_color=BAR_ARM)
    if screenshot_mode and not screenshot_phase_down and now<screenshot_arm_until:
        rest=max(0.0,screenshot_arm_until-now)
        hint.configure(text=f"SHOT: prêt dans {rest:.1f}s — placez-vous"); bar.configure(progress_color=BAR_ARM)
    if col_mode and now<col_arm_until:
        rest=max(0.0,col_arm_until-now)
        hint.configure(text=f"COL: prêt dans {rest:.1f}s — placez-vous"); bar.configure(progress_color=BAR_ARM)
    bar.set(progress_value); root.after(50,update_progress)

# ---- Drag ----
_drag={"x":0,"y":0}
def start_drag(e): _drag["x"],_drag["y"]=e.x,e.y
def on_drag(e): root.geometry(f"+{root.winfo_x()+e.x-_drag['x']}+{root.winfo_y()+e.y-_drag['y']}")

# ---- Création HUD ----
root=ctk.CTk(); root.overrideredirect(True); root.attributes("-topmost",True)
sw,sh=root.winfo_screenwidth(),root.winfo_screenheight()
root.geometry(f"{HUD_W}x{HUD_H}+{sw-HUD_W-HUD_MARGIN}+{HUD_MARGIN}")

wrap=ctk.CTkFrame(root,corner_radius=HUD_CORNER); wrap.pack(fill="both",expand=True)

# Drag global
wrap.bind("<Button-1>", start_drag)
wrap.bind("<B1-Motion>", on_drag)
root.bind("<Button-1>", start_drag)
root.bind("<B1-Motion>", on_drag)

header=ctk.CTkFrame(wrap,fg_color="transparent"); header.pack(fill="x",padx=8,pady=HEADER_PADY)
status_lbl=ctk.CTkLabel(header,text="ON"); status_lbl.pack(side="left")
dot_lbl=ctk.CTkLabel(header,text="●",text_color="#2ecc71"); dot_lbl.pack(side="left",padx=(4,8))
info_lbl=ctk.CTkLabel(header,text=f"• {dwell_delay:.1f}s • {DEADZONE_RADIUS}px • CLICK"); info_lbl.pack(side="left")
close_btn=ctk.CTkButton(header,text="✕",width=CLOSE_BTN_W,height=CLOSE_BTN_H,
                        corner_radius=CLOSE_BTN_CORNER,
                        fg_color="#aa3333",hover_color="#992222",command=root.destroy)
close_btn.pack(side="right")

row=ctk.CTkFrame(wrap,fg_color="transparent"); row.pack(side="top",padx=8,pady=ROW_PADY)
make_dwell_button(row,"ON/OFF",toggle_running)
make_dwell_button(row,"SEL",toggle_selection)
make_dwell_button(row,"SHOT",start_shot)
make_dwell_button(row,"COL",start_col)

hint=ctk.CTkLabel(wrap,text="",font=("Consolas",10))
hint.pack(side="top",padx=6,pady=HINT_PADY)
bar=ctk.CTkProgressBar(wrap,height=BAR_HEIGHT,corner_radius=BAR_CORNER); bar.set(0.0)
bar.configure(progress_color=BAR_DEFAULT); bar.pack(fill="x",padx=8,pady=BAR_PADY)

def keep_on_top():
    try: root.attributes("-topmost",True); root.lift()
    finally: root.after(2000,keep_on_top)
keep_on_top()

threading.Thread(target=dwell_loop,daemon=True).start()
refresh_status(); update_progress(); root.mainloop()
o
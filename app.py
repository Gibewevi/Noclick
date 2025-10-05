# app.py — HUD + dwell + auto-click + VOICE + SEL + SHOT + COLA + COL + COP + DRG
import customtkinter as ctk
import pyautogui
import time
import threading
import logging

from config import (
    HUD_W, HUD_H, HUD_MARGIN, HUD_CORNER,
    BTN_W, BTN_H, BTN_CORNER, BTN_FONT,
    CLOSE_BTN_W, CLOSE_BTN_H, CLOSE_BTN_CORNER,
    HEADER_PADY, ROW_PADY, HINT_PADY, BAR_PADY,
    BAR_HEIGHT, BAR_CORNER, BAR_DEFAULT, BAR_OK, BAR_ARM,
    USE_OS_SNIPPER, SHOT_ARM_SECONDS, SEL_ARM_SECONDS,
    COL_ARM_SECONDS, COL_TIMEOUT_SECS,
    COLA_ARM_SECONDS, COLA_TIMEOUT_SECS,
    DWELL_DELAY_INIT, DEADZONE_RADIUS, MOVE_EPS,
    COP_ARM_SECONDS, COP_TIMEOUT_SECS,
    DRG_ARM_SECONDS,  # ← ajouté
)

from utils import (
    inside_deadzone, kb_copy, kb_select_all, kb_paste, delete_or_backspace,
    kb_copy_all,  # wrapper Ctrl+A puis Ctrl+C
)

from capture import screenshot_to_clipboard
from gpt_voice import GptVoice  # module VOICE déjà OK

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | [%(name)s] %(message)s"
)
log = logging.getLogger("APP")


class NoClicApp:
    def __init__(self):
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        # --- états généraux ---
        self.running = True
        self.dwell_delay = DWELL_DELAY_INIT
        self.progress_value = 0.0

        # --- ancre / deadzone pour CLICK ---
        self.anchor_point = None
        self.rearm_in_deadzone = False

        # --- SEL state ---
        self.selection_mode = False
        self.selection_phase_down = False  # False=pas encore appuyé ; True=mouseDown fait
        self.selection_arm_until = 0.0

        # --- SHOT state (2 immobilités : lock puis validation) ---
        self.screenshot_mode = False
        self.screenshot_phase_down = False
        self.screenshot_arm_until = 0.0
        self.shot_anchor = None

        # --- COLA (coller en remplaçant tout) ---
        self.cola_mode = False
        self.cola_arm_until = 0.0
        self.cola_started_at = 0.0

        # --- COL (coller simple) ---
        self.col_mode = False
        self.col_arm_until = 0.0
        self.col_started_at = 0.0

        # --- COP (copie intégrale) ---
        self.cop_mode = False
        self.cop_arm_until = 0.0
        self.cop_started_at = 0.0

        # --- DRG (drag maintenu) ---
        self.drg_mode = False
        self.drg_arm_until = 0.0
        self.drg_holding = False  # False = pas encore mouseDown ; True = mouseDown maintenu

        # --- UI ---
        self.root = ctk.CTk()
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        self.root.geometry(f"{HUD_W}x{HUD_H}+{sw-HUD_W-HUD_MARGIN}+{HUD_MARGIN}")

        self.wrap = ctk.CTkFrame(self.root, corner_radius=HUD_CORNER)
        self.wrap.pack(fill="both", expand=True)

        # Drag sécurisé (ne pas “tirer” quand on est sur le picker VOICE)
        self._drag = {"x": 0, "y": 0}
        self._drag_active = False
        self.wrap.bind("<Button-1>", self._start_drag)
        self.wrap.bind("<B1-Motion>", self._on_drag)
        self.wrap.bind("<ButtonRelease-1>", self._end_drag)
        self.root.bind("<Button-1>", self._start_drag)
        self.root.bind("<B1-Motion>", self._on_drag)
        self.root.bind("<ButtonRelease-1>", self._end_drag)

        header = ctk.CTkFrame(self.wrap, fg_color="transparent")
        header.pack(fill="x", padx=8, pady=HEADER_PADY)

        self.status_lbl = ctk.CTkLabel(header, text="ON")
        self.status_lbl.pack(side="left")

        self.dot_lbl = ctk.CTkLabel(header, text="●", text_color="#2ecc71")
        self.dot_lbl.pack(side="left", padx=(4, 8))

        self.info_lbl = ctk.CTkLabel(header, text=self._info_text("CLICK"))
        self.info_lbl.pack(side="left")

        close_btn = ctk.CTkButton(
            header, text="✕", width=CLOSE_BTN_W, height=CLOSE_BTN_H,
            corner_radius=CLOSE_BTN_CORNER, fg_color="#aa3333",
            hover_color="#992222", command=self.root.destroy
        )
        close_btn.pack(side="right")

        row = ctk.CTkFrame(self.wrap, fg_color="transparent")
        row.pack(side="top", padx=8, pady=ROW_PADY)
        self._make_dwell_button(row, "ON/OFF", self._toggle_running)
        self._make_dwell_button(row, "SEL",    self._toggle_selection)
        self._make_dwell_button(row, "SHOT",   self._start_shot)
        self._make_dwell_button(row, "COL",    self._start_col)    # coller simple
        self._make_dwell_button(row, "COLA",   self._start_cola)   # coller en remplaçant tout (ex- COL)
        self._make_dwell_button(row, "COP",    self._start_cop)    # copier intégral
        self._make_dwell_button(row, "DRG",    self._start_drg)    # ← nouveau bouton Drag maintenu
        self._make_dwell_button(row, "VOICE",  self._start_voice)

        self.hint = ctk.CTkLabel(self.wrap, text="", font=("Consolas", 10))
        self.hint.pack(side="top", padx=6, pady=HINT_PADY)

        self.bar = ctk.CTkProgressBar(self.wrap, height=BAR_HEIGHT, corner_radius=BAR_CORNER)
        self.bar.set(0.0)
        self.bar.configure(progress_color=BAR_DEFAULT)
        self.bar.pack(fill="x", padx=8, pady=BAR_PADY)

        # VOICE (module externe conservé)
        self.gpt = GptVoice(self.root, self.wrap, self.hint, self.bar, self._set_mode_cb)

        self._keep_on_top()
        threading.Thread(target=self._dwell_loop, daemon=True).start()
        self._refresh_status()
        self._update_progress()

    # ---------------------- UI helpers ----------------------
    def _info_text(self, mode):
        return f"• {self.dwell_delay:.1f}s • {DEADZONE_RADIUS}px • {mode}"

    def _make_dwell_button(self, parent, label, command):
        btn = ctk.CTkButton(parent, text=label, width=BTN_W, height=BTN_H,
                            corner_radius=BTN_CORNER, font=BTN_FONT)
        btn._after = None
        def on_enter(_):
            btn._after = self.root.after(550, command)
        def on_leave(_):
            if btn._after:
                self.root.after_cancel(btn._after)
                btn._after = None
        btn.bind("<Enter>", on_enter)
        btn.bind("<Leave>", on_leave)
        btn.pack(side="left", padx=4, pady=0)
        return btn

    def _set_mode_cb(self, mode_text: str):
        self.info_lbl.configure(text=self._info_text(mode_text))

    def _refresh_status(self):
        self.status_lbl.configure(text="ON" if self.running else "OFF")
        self.dot_lbl.configure(text_color="#2ecc71" if self.running else "#e74c3c")
        if self.cola_mode:
            mode = "COLA"
        elif self.col_mode:
            mode = "COL"
        elif self.cop_mode:
            mode = "COP"
        elif self.drg_mode:
            mode = "DRG"
        elif self.selection_mode:
            mode = "SEL"
        elif self.screenshot_mode:
            mode = "SHOT"
        elif self.gpt.enabled:
            mode = "VOICE"
        else:
            mode = "CLICK"
        self.info_lbl.configure(text=self._info_text(mode))

    def _keep_on_top(self):
        try:
            self.root.attributes("-topmost", True)
            self.root.lift()
        finally:
            self.root.after(2000, self._keep_on_top)

    # Bloque le drag quand on clique dans le picker VOICE
    def _is_descendant(self, parent, child):
        try:
            w = child
            while w is not None:
                if w == parent:
                    return True
                w = w.master
        except Exception:
            pass
        return False

    def _should_block_drag(self, widget):
        try:
            for attr in ("_picker_row", "_device_menu"):
                w = getattr(self.gpt, attr, None)
                if w is not None and self._is_descendant(w, widget):
                    return True
        except Exception:
            pass
        return False

    def _start_drag(self, e):
        if self._should_block_drag(e.widget):
            log.info("[APP] suppress window drag on VOICE picker")
            self._drag_active = False
            return
        self._drag["x"], self._drag["y"] = e.x, e.y
        self._drag_active = True

    def _on_drag(self, e):
        if not self._drag_active:
            return
        self.root.geometry(f"+{self.root.winfo_x()+e.x-self._drag['x']}+{self.root.winfo_y()+e.y-self._drag['y']}")

    def _end_drag(self, _e):
        self._drag_active = False

    # ---------------------- Mode toggles ----------------------
    def _toggle_running(self):
        self.running = not self.running
        self._refresh_status()

    def _toggle_selection(self):
        self._reset_shot()
        self.cola_mode = False
        self.col_mode = False
        self.cop_mode = False
        self.drg_mode = False
        self.drg_holding = False
        self.gpt.stop()
        self.selection_mode = not self.selection_mode
        self.selection_phase_down = False
        self.selection_arm_until = time.time() + SEL_ARM_SECONDS if self.selection_mode else 0.0
        if self.selection_mode:
            self.hint.configure(text=f"SEL: prêt dans {SEL_ARM_SECONDS:.1f}s — placez-vous au début du texte")
            self.bar.configure(progress_color=BAR_ARM)
            self._set_mode_cb("SEL")
        else:
            self.hint.configure(text="")
            self.bar.configure(progress_color=BAR_DEFAULT)
            self._set_mode_cb("CLICK")
        self._refresh_status()

    def _reset_shot(self):
        self.screenshot_mode = False
        self.screenshot_phase_down = False
        self.shot_anchor = None
        self.hint.configure(text="")
        self.bar.configure(progress_color=BAR_DEFAULT)

    def _start_shot(self):
        if self.selection_mode:
            self._toggle_selection()
        self.cola_mode = False
        self.col_mode = False
        self.cop_mode = False
        self.drg_mode = False
        self.drg_holding = False
        self.gpt.stop()
        self.screenshot_mode = True
        self.screenshot_phase_down = False
        self.shot_anchor = None
        self.screenshot_arm_until = time.time() + SHOT_ARM_SECONDS
        self.hint.configure(text=f"SHOT: prêt dans {SHOT_ARM_SECONDS:.1f}s — placez-vous")
        self.bar.configure(progress_color=BAR_ARM)
        self._set_mode_cb("SHOT")
        self._refresh_status()

    def _start_cola(self):
        """Armement puis Ctrl+A / Delete / Ctrl+V (remplacement intégral)."""
        self.selection_mode = False
        self.screenshot_mode = False
        self.col_mode = False
        self.cop_mode = False
        self.drg_mode = False
        self.drg_holding = False
        self.gpt.stop()
        self.cola_mode = True
        self.cola_started_at = time.time()
        self.cola_arm_until = self.cola_started_at + COLA_ARM_SECONDS
        self.hint.configure(text=f"COLA: prêt dans {COLA_ARM_SECONDS:.1f}s — placez-vous")
        self.bar.configure(progress_color=BAR_ARM)
        self._set_mode_cb("COLA")
        self._refresh_status()

    def _start_col(self):
        """Armement puis Ctrl+V (coller simple, sans suppression préalable)."""
        self.selection_mode = False
        self.screenshot_mode = False
        self.cola_mode = False
        self.cop_mode = False
        self.drg_mode = False
        self.drg_holding = False
        self.gpt.stop()
        self.col_mode = True
        self.col_started_at = time.time()
        self.col_arm_until = self.col_started_at + COL_ARM_SECONDS
        self.hint.configure(text=f"COL: prêt dans {COL_ARM_SECONDS:.1f}s — placez-vous")
        self.bar.configure(progress_color=BAR_ARM)
        self._set_mode_cb("COL")
        self._refresh_status()

    def _start_cop(self):
        """Armement puis Ctrl+A / Ctrl+C (sans supprimer, sans coller)."""
        self.selection_mode = False
        self.screenshot_mode = False
        self.cola_mode = False
        self.col_mode = False
        self.drg_mode = False
        self.drg_holding = False
        self.gpt.stop()
        self.cop_mode = True
        self.cop_started_at = time.time()
        self.cop_arm_until = self.cop_started_at + COP_ARM_SECONDS
        self.hint.configure(text=f"COP: prêt dans {COP_ARM_SECONDS:.1f}s — placez-vous")
        self.bar.configure(progress_color=BAR_ARM)
        self._set_mode_cb("COP")
        self._refresh_status()

    def _start_drg(self):
        """Armement → immobilité = mouseDown → tu déplaces → re-immobilité = mouseUp."""
        self.selection_mode = False
        self.screenshot_mode = False
        self.cola_mode = False
        self.col_mode = False
        self.cop_mode = False
        self.gpt.stop()
        self.drg_mode = True
        self.drg_holding = False
        self.drg_arm_until = time.time() + DRG_ARM_SECONDS
        self.hint.configure(text=f"DRG: prêt dans {DRG_ARM_SECONDS:.1f}s — placez-vous sur l’élément à déplacer")
        self.bar.configure(progress_color=BAR_ARM)
        self._set_mode_cb("DRG")
        self._refresh_status()

    def _start_voice(self):
        self.selection_mode = False
        self.screenshot_mode = False
        self.cola_mode = False
        self.col_mode = False
        self.cop_mode = False
        self.drg_mode = False
        self.drg_holding = False
        self.gpt.toggle()
        self._refresh_status()

    # ---------------------- Progress UI tick ----------------------
    def _update_progress(self):
        now = time.time()
        self.gpt.update_progress(now)
        self.bar.set(self.progress_value)
        self.root.after(50, self._update_progress)

    # ---------------------- Dwell engine ----------------------
    def _dwell_loop(self):
        prev = pyautogui.position()
        t0 = time.time()

        while True:
            pos = pyautogui.position()
            moved = (abs(pos[0]-prev[0]) + abs(pos[1]-prev[1])) > MOVE_EPS
            now = time.time()

            # VOICE peut consommer le dwell pendant rec/paste
            if self.gpt.on_idle(now, pos):
                log.info("[APP] dwell consumed by VOICE")
                prev = pos
                t0 = now
                self.progress_value = 0.0
                time.sleep(0.05)
                continue

            # ------------ SEL mode ------------
            if self.selection_mode:
                if now < self.selection_arm_until:
                    rest = self.selection_arm_until - now
                    self.hint.configure(text=f"SEL: prêt dans {rest:.1f}s — placez-vous au début du texte")
                    self.bar.configure(progress_color=BAR_ARM)
                    self.progress_value = max(0.0, min(1.0, 1.0 - rest / max(SEL_ARM_SECONDS, 0.001)))
                    time.sleep(0.05)
                    prev = pos
                    continue

                if moved:
                    prev = pos
                    t0 = now
                    self.progress_value = 0.0
                    time.sleep(0.05)
                    continue

                elapsed = now - t0
                ratio = max(0.0, min(elapsed / self.dwell_delay, 1.0))
                self.progress_value = ratio
                if ratio >= 1.0:
                    if not self.selection_phase_down:
                        try:
                            pyautogui.mouseDown(pos[0], pos[1])
                            log.info("[APP] SEL: mouseDown @ (%d,%d)", pos[0], pos[1])
                            self.hint.configure(text="SEL: maintiens & déplace. Immobilise pour relâcher + copier")
                            self.bar.configure(progress_color=BAR_OK)
                            self.selection_phase_down = True
                        except Exception as e:
                            log.exception("SEL mouseDown failed: %s", e)
                    else:
                        try:
                            pyautogui.mouseUp(pos[0], pos[1])
                            log.info("[APP] SEL: mouseUp @ (%d,%d)", pos[0], pos[1])
                            time.sleep(0.06)
                            kb_copy()
                            log.info("[APP] SEL: copied to clipboard")
                            self.hint.configure(text="SEL: copié ✓")
                        except Exception as e:
                            log.exception("SEL finalize failed: %s", e)
                            self.hint.configure(text="SEL: erreur (voir logs)")
                        self.selection_mode = False
                        self.selection_phase_down = False
                        self.bar.configure(progress_color=BAR_DEFAULT)
                        self._set_mode_cb("CLICK")
                        self._refresh_status()
                    t0 = now
                    self.progress_value = 0.0
                    time.sleep(0.08)
                time.sleep(0.05)
                continue

            # ------------ SHOT mode (rectangulaire en 2 immobilités) ------------
            if self.screenshot_mode:
                if now < self.screenshot_arm_until and not self.screenshot_phase_down:
                    rest = self.screenshot_arm_until - now
                    self.hint.configure(text=f"SHOT: prêt dans {rest:.1f}s — placez-vous")
                    self.bar.configure(progress_color=BAR_ARM)
                    self.progress_value = max(0.0, min(1.0, 1.0 - rest / max(SHOT_ARM_SECONDS, 0.001)))
                    time.sleep(0.05)
                    prev = pos
                    continue

                if moved:
                    prev = pos
                    t0 = now
                    self.progress_value = 0.0
                    time.sleep(0.05)
                    continue

                elapsed = now - t0
                ratio = max(0.0, min(elapsed / self.dwell_delay, 1.0))
                self.progress_value = ratio
                if ratio >= 1.0:
                    try:
                        if USE_OS_SNIPPER and not self.screenshot_phase_down:
                            pyautogui.hotkey('win', 'shift', 's')
                            log.info("[APP] SHOT: Windows snipping tool opened (Win+Shift+S)")
                            self.hint.configure(text="SHOT: outil de capture ouvert — dessinez la zone à capturer")
                            self._reset_shot()
                            self._set_mode_cb("CLICK")
                            self._refresh_status()
                        else:
                            if not self.screenshot_phase_down:
                                self.shot_anchor = (pos[0], pos[1])
                                self.screenshot_phase_down = True
                                self.hint.configure(text="SHOT: lock ✓ → déplacez puis immobilisez pour valider")
                                self.bar.configure(progress_color=BAR_OK)
                                log.info("[APP] SHOT: anchor @ (%d,%d)", pos[0], pos[1])
                            else:
                                x1, y1 = self.shot_anchor
                                x2, y2 = pos[0], pos[1]
                                ok, msg = screenshot_to_clipboard(x1, y1, x2, y2)
                                self.hint.configure(text=msg)
                                log.info("[APP] SHOT: %s", msg)
                                self._reset_shot()
                                self._set_mode_cb("CLICK")
                                self._refresh_status()
                    except Exception as e:
                        log.exception("SHOT failed: %s", e)
                        self.hint.configure(text="SHOT: erreur (voir logs)")
                        self._reset_shot()
                        self._set_mode_cb("CLICK")
                        self._refresh_status()
                    t0 = now
                    self.progress_value = 0.0
                    time.sleep(0.2)
                time.sleep(0.05)
                continue

            # ------------ COLA mode (remplacement intégral) ------------
            if self.cola_mode:
                if now - self.cola_started_at > COLA_TIMEOUT_SECS:
                    self.cola_mode = False
                    self.bar.configure(progress_color=BAR_DEFAULT)
                    self.hint.configure(text="COLA: délai dépassé")
                    self._set_mode_cb("CLICK")
                    self._refresh_status()
                    time.sleep(0.05)
                    continue

                if now < self.cola_arm_until:
                    rest = self.cola_arm_until - now
                    self.hint.configure(text=f"COLA: prêt dans {rest:.1f}s — placez-vous")
                    self.bar.configure(progress_color=BAR_ARM)
                    self.progress_value = max(0.0, min(1.0, 1.0 - rest / max(COLA_ARM_SECONDS, 0.001)))
                    time.sleep(0.05)
                    prev = pos
                    continue

                if moved:
                    prev = pos
                    t0 = now
                    self.progress_value = 0.0
                    time.sleep(0.05)
                    continue

                elapsed = now - t0
                ratio = max(0.0, min(elapsed / self.dwell_delay, 1.0))
                self.progress_value = ratio
                if ratio >= 1.0:
                    try:
                        pyautogui.click(pos[0], pos[1])   # focus
                        time.sleep(0.06)
                        kb_select_all()
                        time.sleep(0.02)
                        delete_or_backspace()
                        time.sleep(0.02)
                        kb_paste()
                        log.info("[APP] COLA: pasted clipboard (full replace)")
                        self.hint.configure(text="COLA: collé ✓")
                    except Exception as e:
                        log.exception("COLA failed: %s", e)
                        self.hint.configure(text="COLA: erreur (voir logs)")
                    self.cola_mode = False
                    self.bar.configure(progress_color=BAR_DEFAULT)
                    self._set_mode_cb("CLICK")
                    self._refresh_status()
                    t0 = now
                    self.progress_value = 0.0
                    time.sleep(0.1)
                time.sleep(0.05)
                continue

            # ------------ COL mode (coller simple) ------------
            if self.col_mode:
                if now - self.col_started_at > COL_TIMEOUT_SECS:
                    self.col_mode = False
                    self.bar.configure(progress_color=BAR_DEFAULT)
                    self.hint.configure(text="COL: délai dépassé")
                    self._set_mode_cb("CLICK")
                    self._refresh_status()
                    time.sleep(0.05)
                    continue

                if now < self.col_arm_until:
                    rest = self.col_arm_until - now
                    self.hint.configure(text=f"COL: prêt dans {rest:.1f}s — placez-vous")
                    self.bar.configure(progress_color=BAR_ARM)
                    self.progress_value = max(0.0, min(1.0, 1.0 - rest / max(COL_ARM_SECONDS, 0.001)))
                    time.sleep(0.05)
                    prev = pos
                    continue

                if moved:
                    prev = pos
                    t0 = now
                    self.progress_value = 0.0
                    time.sleep(0.05)
                    continue

                elapsed = now - t0
                ratio = max(0.0, min(elapsed / self.dwell_delay, 1.0))
                self.progress_value = ratio
                if ratio >= 1.0:
                    try:
                        pyautogui.click(pos[0], pos[1])   # focus
                        time.sleep(0.06)
                        kb_paste()                         # coller uniquement
                        log.info("[APP] COL: pasted clipboard (simple)")
                        self.hint.configure(text="COL: collé ✓")
                    except Exception as e:
                        log.exception("COL failed: %s", e)
                        self.hint.configure(text="COL: erreur (voir logs)")
                    self.col_mode = False
                    self.bar.configure(progress_color=BAR_DEFAULT)
                    self._set_mode_cb("CLICK")
                    self._refresh_status()
                    t0 = now
                    self.progress_value = 0.0
                    time.sleep(0.1)
                time.sleep(0.05)
                continue

            # ------------ COP mode (copier tout) ------------
            if self.cop_mode:
                if now - self.cop_started_at > COP_TIMEOUT_SECS:
                    self.cop_mode = False
                    self.bar.configure(progress_color=BAR_DEFAULT)
                    self.hint.configure(text="COP: délai dépassé")
                    self._set_mode_cb("CLICK")
                    self._refresh_status()
                    time.sleep(0.05)
                    continue

                if now < self.cop_arm_until:
                    rest = self.cop_arm_until - now
                    self.hint.configure(text=f"COP: prêt dans {rest:.1f}s — placez-vous")
                    self.bar.configure(progress_color=BAR_ARM)
                    self.progress_value = max(0.0, min(1.0, 1.0 - rest / max(COP_ARM_SECONDS, 0.001)))
                    time.sleep(0.05)
                    prev = pos
                    continue

                if moved:
                    prev = pos
                    t0 = now
                    self.progress_value = 0.0
                    time.sleep(0.05)
                    continue

                elapsed = now - t0
                ratio = max(0.0, min(elapsed / self.dwell_delay, 1.0))
                self.progress_value = ratio
                if ratio >= 1.0:
                    try:
                        pyautogui.click(pos[0], pos[1])   # focus
                        time.sleep(0.06)
                        kb_copy_all()                     # Ctrl+A puis Ctrl+C
                        log.info("[APP] COP: copied selection (Ctrl+A then Ctrl+C)")
                        self.hint.configure(text="COP: copié ✓")
                    except Exception as e:
                        log.exception("COP failed: %s", e)
                        self.hint.configure(text="COP: erreur (voir logs)")
                    self.cop_mode = False
                    self.bar.configure(progress_color=BAR_DEFAULT)
                    self._set_mode_cb("CLICK")
                    self._refresh_status()
                    t0 = now
                    self.progress_value = 0.0
                    time.sleep(0.1)
                time.sleep(0.05)
                continue

            # ------------ DRG mode (drag maintenu) ------------
            if self.drg_mode:
                # Armement initial (tu te places sur la zone à “attraper”)
                if not self.drg_holding and now < self.drg_arm_until:
                    rest = self.drg_arm_until - now
                    self.hint.configure(text=f"DRG: prêt dans {rest:.1f}s — placez-vous sur l’élément à déplacer")
                    self.bar.configure(progress_color=BAR_ARM)
                    self.progress_value = max(0.0, min(1.0, 1.0 - rest / max(DRG_ARM_SECONDS, 0.001)))
                    time.sleep(0.05)
                    prev = pos
                    continue

                # Après armement : 1ère immobilité => mouseDown
                if not self.drg_holding:
                    if moved:
                        prev = pos
                        t0 = now
                        self.progress_value = 0.0
                        time.sleep(0.05)
                        continue
                    elapsed = now - t0
                    ratio = max(0.0, min(elapsed / self.dwell_delay, 1.0))
                    self.progress_value = ratio
                    if ratio >= 1.0:
                        try:
                            pyautogui.mouseDown(pos[0], pos[1])
                            log.info("[APP] DRG: mouseDown @ (%d,%d)", pos[0], pos[1])
                            self.hint.configure(text="DRG: maintiens & déplace. Immobilise pour relâcher")
                            self.bar.configure(progress_color=BAR_OK)
                            self.drg_holding = True
                        except Exception as e:
                            log.exception("DRG mouseDown failed: %s", e)
                            # en cas d’échec, on sort du mode
                            self.drg_mode = False
                            self.drg_holding = False
                            self.bar.configure(progress_color=BAR_DEFAULT)
                            self._set_mode_cb("CLICK")
                            self._refresh_status()
                        t0 = now
                        self.progress_value = 0.0
                        time.sleep(0.08)
                    time.sleep(0.05)
                    continue
                else:
                    # En drag (mouseDown maintenu) : on relâche sur re-immobilité
                    if moved:
                        prev = pos
                        t0 = now
                        self.progress_value = 0.0
                        time.sleep(0.05)
                        continue
                    elapsed = now - t0
                    ratio = max(0.0, min(elapsed / self.dwell_delay, 1.0))
                    self.progress_value = ratio
                    if ratio >= 1.0:
                        try:
                            pyautogui.mouseUp(pos[0], pos[1])
                            log.info("[APP] DRG: mouseUp @ (%d,%d)", pos[0], pos[1])
                            self.hint.configure(text="DRG: relâché ✓")
                        except Exception as e:
                            log.exception("DRG mouseUp failed: %s", e)
                            self.hint.configure(text="DRG: erreur (voir logs)")
                        # Quitte DRG et revient au CLICK
                        self.drg_mode = False
                        self.drg_holding = False
                        self.bar.configure(progress_color=BAR_DEFAULT)
                        self._set_mode_cb("CLICK")
                        self._refresh_status()
                        t0 = now
                        self.progress_value = 0.0
                        time.sleep(0.08)
                    time.sleep(0.05)
                    continue

            # ------------ Mode CLICK (par défaut) avec deadzone ------------
            if self.running:
                if moved:
                    if self.anchor_point and not inside_deadzone(pos, self.anchor_point, DEADZONE_RADIUS):
                        self.rearm_in_deadzone = True
                    prev = pos
                    t0 = now
                    self.progress_value = 0.0
                else:
                    elapsed = now - t0
                    ratio = max(0.0, min(elapsed / self.dwell_delay, 1.0))
                    self.progress_value = ratio
                    if ratio >= 1.0:
                        if (self.anchor_point is None) or \
                           (not inside_deadzone(pos, self.anchor_point, DEADZONE_RADIUS)) or \
                           self.rearm_in_deadzone:
                            try:
                                pyautogui.click(pos[0], pos[1])
                                self.anchor_point = pos
                                self.rearm_in_deadzone = False
                                log.info("[APP] auto-click @ (%d,%d)", pos[0], pos[1])
                            except Exception as e:
                                log.exception("auto-click failed: %s", e)
                        t0 = now
                        self.progress_value = 0.0
                        time.sleep(0.08)
            else:
                self.progress_value = 0.0
                time.sleep(0.05)

            time.sleep(0.05)

    def run(self):
        self.root.mainloop()

# app.py — HUD + dwell + auto-click + VOICE + SEL + SHOT + COLA + COL + COP + DRG
from gpt_voice import GptVoice  # module VOICE déjà OK
from capture import screenshot_to_clipboard
from utils import (
    inside_deadzone,
    kb_copy,
    kb_select_all,
    kb_paste,
    delete_or_backspace,
    kb_copy_all,  # wrapper Ctrl+A puis Ctrl+C
)
import customtkinter as ctk
import pyautogui
import time
import threading
import logging
import json
import io
import ctypes
from ctypes import wintypes
from pathlib import Path
from PIL import Image, ImageDraw, ImageColor

from config import (
    HUD_W,
    HUD_H,
    HUD_MARGIN,
    HUD_CORNER,
    BTN_W,
    BTN_H,
    BTN_CORNER,
    BTN_FONT,
    PLUS_SIZE,
    PLUS_CORNER,
    PLUS_FONT,
    CLOSE_BTN_W,
    CLOSE_BTN_H,
    CLOSE_BTN_CORNER,
    HEADER_PADY,
    ROW_PADY,
    HINT_PADY,
    BAR_PADY,
    BAR_HEIGHT,
    BAR_CORNER,
    BAR_DEFAULT,
    BAR_OK,
    BAR_ARM,
    SHELF_PADY,
    SHELF_CORNER,
    SHELF_BTN_W,
    SHELF_BTN_H,
    SHELF_BTN_FONT,
    SHELF_BTN_FG,
    SHELF_BTN_HOVER,
    SHELF_BTN_TEXT,
    USE_OS_SNIPPER,
    SHOT_ARM_SECONDS,
    SEL_ARM_SECONDS,
    COL_ARM_SECONDS,
    COL_TIMEOUT_SECS,
    COLA_ARM_SECONDS,
    COLA_TIMEOUT_SECS,
    DWELL_DELAY_INIT,
    DEADZONE_RADIUS,
    MOVE_EPS,
    COP_ARM_SECONDS,
    COP_TIMEOUT_SECS,
    DRG_ARM_SECONDS,
    DEL_ARM_SECONDS,
    DEL_TIMEOUT_SECS,
    ENT_ARM_SECONDS,
    ENT_TIMEOUT_SECS,
    PYTH_ARM_SECONDS,
    PYTH_TIMEOUT_SECS,
    SCROLL_STEP,
    SCROLL_INTERVAL,
    CLICD_ARM_SECONDS,
    CLICD_TIMEOUT_SECS,
)

WM_MOUSEWHEEL = 0x020A
WHEEL_DELTA = 120
SMTO_ABORTIFHUNG = 0x0002
SMTO_NORMAL = 0x0000
GA_ROOT = 2


logging.basicConfig(
    level=logging.INFO, format="%(asctime)s | %(levelname)s | [%(name)s] %(message)s"
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
        self.selection_phase_down = (
            False  # False=pas encore appuyé ; True=mouseDown fait
        )
        self.selection_arm_until = 0.0

        # --- SELCP state ---
        self.selcp_mode = False
        self.selcp_phase_down = False
        self.selcp_arm_until = 0.0

        # --- SELDL state ---
        self.seldl_mode = False
        self.seldl_phase_down = False
        self.seldl_arm_until = 0.0

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

        # --- CLICD (clic droit après immobilisation) ---
        self.clicd_mode = False
        self.clicd_arm_until = 0.0
        self.clicd_started_at = 0.0

        # --- DRG (drag maintenu) ---
        self.drg_mode = False
        self.drg_arm_until = 0.0
        self.drg_holding = (
            False  # False = pas encore mouseDown ; True = mouseDown maintenu
        )

        # --- DEL (supprime tout) ---
        self.del_mode = False
        self.del_arm_until = 0.0
        self.del_started_at = 0.0

        # --- ENT (Entrée) ---
        self.ent_mode = False
        self.ent_arm_until = 0.0
        self.ent_started_at = 0.0

        # --- PYTH (écrire python main.py) ---
        self.pyth_mode = False
        self.pyth_arm_until = 0.0
        self.pyth_started_at = 0.0

        # --- CSHARP (écrire et exécuter commande C#) ---
        self.csharp_mode = False
        self.csharp_arm_until = 0.0
        self.csharp_started_at = 0.0

        # --- UI ---
        self.root = ctk.CTk()
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        self.root.geometry(
            f"{HUD_W}x{HUD_H}+{sw-HUD_W-HUD_MARGIN}+{HUD_MARGIN}")

        self._icon_cache = {}
        self._svg_warning_emitted = False
        self._svg_fallback_warning_emitted = False
        try:
            self._icon_root = Path(__file__).with_name("svg")
        except Exception:
            self._icon_root = None
        self._pending_icon_updates = set()
        self._preload_icons(["COP", "DRG", "VOICE"])
        self._pending_icon_updates.update(["COP", "DRG", "VOICE"])

        self.wrap = ctk.CTkFrame(self.root, corner_radius=HUD_CORNER)
        self.wrap.pack(fill="both", expand=True)

        self._hud_windows = set()
        try:
            self.root.update_idletasks()
            self._hud_hwnd = int(self.root.winfo_id())
            self._register_hud_window(self._hud_hwnd)
        except Exception:
            self._hud_hwnd = None
        self._scroll_target_hwnd = None
        self._scroll_target_point = None
        self._last_outside_point = None
        self._last_outside_hwnd = None

        # Drag sécurisé (ne pas "tirer" quand on est sur le picker VOICE)
        self._drag = {"x": 0, "y": 0}
        self._drag_active = False
        # DRG interne pour le drag & drop d’extensions depuis la toolbar
        self._drag_toolbar_key = None
        self._drag_toolbar_ghost = None
        self._suspend_dwell_actions = 0
        self._minimized = False
        self._minimized_children = []
        self._normal_size = None
        self._scroll_buttons = []
        self._hover_hint_owner = None
        self._hover_hint_backup = ""
        self._hover_restore_delay = DWELL_DELAY_INIT
        self._hover_restore_color = BAR_DEFAULT
        self._in_extension_hover = False
        self._extension_buttons = {}
        self._highlighted_extensions = set()
        self._current_mode = "CLICK"

        self.header = ctk.CTkFrame(self.wrap, fg_color="transparent")
        self.header.pack(fill="x", padx=8, pady=HEADER_PADY)
        # Bind drag sur lentete et via root (garde)
        self.header.bind("<Button-1>", self._start_drag)
        self.header.bind("<B1-Motion>", self._on_drag)
        self.header.bind("<ButtonRelease-1>", self._end_drag)
        self._drag_header = self.header
        self.root.bind("<Button-1>", self._start_drag)
        self.root.bind("<B1-Motion>", self._on_drag)
        self.root.bind("<ButtonRelease-1>", self._end_drag)
        self.root.bind(
            "<Leave>",
            lambda e: (self._stop_all_scrolls(), self._exit_extension_hover()),
            add="+",
        )

        self.status_lbl = ctk.CTkLabel(self.header, text="ON")
        self.status_lbl.pack(side="left")

        self.dot_lbl = ctk.CTkLabel(
            self.header, text="●", text_color="#2ecc71")
        self.dot_lbl.pack(side="left", padx=(4, 8))

        self.info_lbl = ctk.CTkLabel(
            self.header, text=self._info_text("CLICK"))
        self.info_lbl.pack(side="left")

        self.close_btn = ctk.CTkButton(
            self.header,
            text="X",
            width=CLOSE_BTN_W,
            height=CLOSE_BTN_H,
            corner_radius=CLOSE_BTN_CORNER,
            fg_color="#aa3333",
            hover_color="#992222",
            command=self.root.destroy,
        )
        self.close_btn.pack(side="right", padx=(4, 0))

        self.minimize_btn = ctk.CTkButton(
            self.header,
            text="_",
            width=CLOSE_BTN_W,
            height=CLOSE_BTN_H,
            corner_radius=CLOSE_BTN_CORNER,
            fg_color="#555555",
            hover_color="#444444",
            command=self._toggle_minimize,
        )
        self.minimize_btn.pack(side="right", padx=(0, 4))
        self._update_minimize_button()

        self.config_toggle_frame = ctk.CTkFrame(
            self.header, fg_color="transparent")
        self.config_toggle_frame.pack(side="right", padx=(0, 10))

        self._config_states = [2] + [0] * 3  # 0=hidden, 1=visible, 2=active
        self._config_active = 0
        self._config_buttons = []
        self._build_config_toggles()
        row = ctk.CTkFrame(self.wrap, fg_color="transparent")
        row.pack(side="top", padx=8, pady=ROW_PADY)
        self._make_dwell_button(
            row, "ON/OFF", self._toggle_running, ext_key="AUTO", hover_mode="instant"
        )
        self._make_dwell_button(
            row, "SEL", self._toggle_selection, ext_key="SEL", hover_mode="instant"
        )
        self._make_dwell_button(
            row, "SHOT", self._start_shot, ext_key="SHOT", hover_mode="instant"
        )
        self._make_dwell_button(
            row, "COL", self._start_col, ext_key="COL", hover_mode="instant"
        )  # coller simple
        self._make_dwell_button(
            row, "COLA", self._start_cola, ext_key="COLA", hover_mode="instant"
        )  # coller en remplaçant tout (ex- COL)
        self._make_dwell_button(
            row, "COP", self._start_cop, ext_key="COP", hover_mode="instant"
        )  # copier intégral
        self._make_dwell_button(
            row, "DRG", self._start_drg, ext_key="DRG", hover_mode="instant"
        )  # ? nouveau bouton Drag maintenu
        self._make_dwell_button(
            row, "VOICE", self._start_voice, ext_key="VOICE", hover_mode="instant"
        )
        try:
            self.root.after_idle(self._apply_pending_icon_updates)
        except Exception:
            pass
        try:
            self.root.update_idletasks()
            self._apply_pending_icon_updates()
        except Exception:
            pass

        # Transform features into extensions (dynamic toolbar)
        self._extensions = {
            "AUTO": {
                "label": "ON/OFF",
                "handler": self._toggle_running,
                "hint": "Active ou desactive l'autoclick",
            },
            "SEL": {
                "label": "SEL",
                "handler": self._toggle_selection,
                "hint": "Selection par immobilisation puis copie",
            },
            "SELCP": {
                "label": "SELCP",
                "handler": self._start_selcp,
                "hint": "Selection + copie automatique",
            },
            "SELDL": {
                "label": "SELDL",
                "handler": self._start_seldl,
                "hint": "Selectionne et supprime le texte",
            },
            "SHOT": {
                "label": "SHOT",
                "handler": self._start_shot,
                "hint": "Prepare une capture d'ecran",
            },
            "COL": {
                "label": "COL",
                "handler": self._start_col,
                "hint": "Colle le presse papier sans effacer",
            },
            "COLA": {
                "label": "COLA",
                "handler": self._start_cola,
                "hint": "Colle apres selection totale",
            },
            "COP": {
                "label": "COP",
                "handler": self._start_cop,
                "hint": "Copie integralement le texte cible",
            },
            "CLICD": {
                "label": "CLICD",
                "handler": self._start_clicd,
                "hint": "Clic droit apres immobilisation",
            },
            "ENT": {
                "label": "ENT",
                "handler": self._start_ent,
                "hint": "Envoie la touche Entree",
            },
            "PYTH": {
                "label": "PYTH",
                "handler": self._start_pyth,
                "command": "python main.py",
                "hint": "Tape puis lance python main.py",
            },
            "CSHARP": {
                "label": "CSH#",
                "handler": self._start_csharp,
                "command": "dotnet run --project ErgoClic.UI",
                "hint": "Tape et lance dotnet run --project ErgoClic.UI",
            },
            "DRG": {
                "label": "DRG",
                "handler": self._start_drg,
                "hint": "Maintient le clic pour deplacer",
            },
            "VOICE": {
                "label": "VOICE",
                "handler": self._start_voice,
                "hint": "Ouvre la dictee vocale",
            },
            "DEL": {
                "label": "DEL",
                "handler": self._start_del,
                "hint": "Selectionne tout puis supprime",
            },
            "SCROLU": {
                "label": "SCROLU",
                "handler": None,
                "hint": "Defile vers le haut tant que survole",
            },
            "D": {
                "label": "SCROLL D",
                "handler": None,
                "hint": "Defile vers le bas tant que survole",
            },
        }
        self._pyth_command = self._extensions.get("PYTH", {}).get(
            "command", "python main.py"
        )
        self._csharp_command = self._extensions.get("CSHARP", {}).get(
            "command", "dotnet run --project ErgoClic.UI"
        )

        # Load active extensions from settings.json
        from utils import user_data_path
        self._settings_path = user_data_path("settings.json")

        try:
            with open(self._settings_path, "r", encoding="utf-8") as f:
                self._settings = json.load(f)
        except Exception:
            self._settings = {}

        # Configuration buttons (states persisted in settings)
        self._config_states = [2] + [0] * 3  # 0=hidden, 1=visible, 2=active
        saved_states = self._settings.get("config_states")
        if isinstance(saved_states, list) and saved_states:
            states = []
            for i in range(4):
                val = 0
                if i < len(saved_states):
                    try:
                        val = int(saved_states[i])
                    except Exception:
                        val = 0
                val = max(0, min(2, val))
                states.append(val)
            if len(states) < 4:
                states.extend([0] * (4 - len(states)))
            else:
                states = states[:4]
            self._config_states = states
        else:
            self._config_states = [2] + [0] * 3
        active_idx = None
        for i, val in enumerate(self._config_states):
            if val == 2:
                if active_idx is None:
                    active_idx = i
                else:
                    self._config_states[i] = 1
        saved_active = self._settings.get("config_active")
        if isinstance(saved_active, int) and 0 <= saved_active < len(
            self._config_states
        ):
            if self._config_states[saved_active] != 0:
                if active_idx is not None and active_idx != saved_active:
                    self._config_states[active_idx] = 1
                self._config_states[saved_active] = 2
                active_idx = saved_active
        self._config_active = active_idx
        try:
            self._refresh_all_config_buttons()
        except Exception:
            pass

        default_active = ["AUTO", "SEL", "COP", "CLICD"]
        self.active_extensions = [
            k
            for k in self._settings.get("active_extensions", default_active)
            if k in self._extensions
        ]
        self._ensure_unique_active_extensions()

        # Floating modules: each small toolbar can contain multiple extensions
        self._modules = {}  # mod_id -> {win, frame, content, keys:list, orient:'h'|'v'}
        self._mod_of_key = {}  # key -> mod_id
        self._next_mod_id = 1

        # Replace static row with dynamic toolbar and plus button
        try:
            row.destroy()
        except Exception:
            pass
        self.hint = ctk.CTkLabel(self.wrap, text="", font=("Consolas", 13))
        self.toolbar_row = ctk.CTkFrame(self.wrap, fg_color="transparent")
        self.toolbar_row.pack(side="top", padx=8, pady=ROW_PADY)
        self._last_width = HUD_W
        self._render_toolbar()

        self.hint.pack(side="top", padx=6, pady=HINT_PADY)

        self.bar = ctk.CTkProgressBar(
            self.wrap, height=BAR_HEIGHT, corner_radius=BAR_CORNER
        )
        self.bar.set(0.0)
        self.bar.configure(progress_color=BAR_DEFAULT)
        self.bar.pack(fill="x", padx=8, pady=BAR_PADY)

        # Bottom shelf for extensions catalogue (hidden by default)
        self._shelf_visible = False
        self._shelf_mode = "all"
        self._shelf_delta_h = 40
        self._last_shelf_h = 0
        self._shelf_row = ctk.CTkFrame(self.wrap, corner_radius=6)
        self._shelf_row.pack_forget()
        self._current_shelf_height = 0
        try:
            self.root.update_idletasks()
            req_h = int(self.root.winfo_reqheight())
            self._base_height = req_h if req_h > 0 else HUD_H
            self._resize_root_height()
        except Exception:
            self._base_height = HUD_H

        # VOICE (module externe conservé)
        self.gpt = GptVoice(
            self.root, self.wrap, self.hint, self.bar, self._set_mode_cb
        )

        self._keep_on_top()
        threading.Thread(target=self._dwell_loop, daemon=True).start()
        self._refresh_status()
        self._update_progress()
        try:
            self.root.after(160, self._refresh_base_height)
        except Exception:
            pass

        # Make label configure ASCII-safe to avoid encoding artifacts on Windows
        try:

            def _wrap_config_ascii(lbl):
                _orig = lbl.configure

                def _safe_config(**kwargs):
                    if "text" in kwargs and kwargs["text"] is not None:
                        try:
                            txt = str(kwargs["text"])
                            txt = "".join(
                                ch for ch in txt if ord(ch) < 128 or ch == "●"
                            )
                            kwargs["text"] = txt
                        except Exception:
                            pass
                    return _orig(**kwargs)

                return _safe_config

            self.hint.configure = _wrap_config_ascii(self.hint)
            self.info_lbl.configure = _wrap_config_ascii(self.info_lbl)
        except Exception:
            pass

        # Restore floating modules (new format), fallback to legacy single list
        try:
            mods = self._settings.get("floating_modules")
            if isinstance(mods, list):
                for m in mods:
                    keys = [k for k in (m.get("keys") or [])
                            if k in self._extensions]
                    if not keys:
                        continue
                    cfg = m.get("config", 0)
                    mod_id = self._create_module_window(
                        m.get("x"), m.get("y"), config_index=cfg
                    )
                    # orientation
                    self._modules.get(mod_id, {}).update(
                        {"orient": (m.get("orient") or "h")}
                    )
                    for k in keys:
                        self._add_key_to_module(mod_id, k)
                    self._repack_module_buttons(mod_id)
                    self._resize_module(mod_id)
            else:
                # legacy: floating_extensions as list of singletons
                for item in self._settings.get("floating_extensions", []) or []:
                    k = item.get("key")
                    if not (k and k in self._extensions):
                        continue
                    mod_id = self._create_module_window(
                        item.get("x"), item.get("y"))
                    self._add_key_to_module(mod_id, k)
                    self._repack_module_buttons(mod_id)
                    self._resize_module(mod_id)
        except Exception:
            log.exception("restore floating modules failed")
        finally:
            try:
                self._apply_config_visibility()
            except Exception:
                pass

    # ---------------------- UI helpers ----------------------
    def _info_text(self, mode):
        return f"{self.dwell_delay:.1f}s | {DEADZONE_RADIUS}px | {mode}"

    def _toggle_minimize(self):
        if self._minimized:
            self._restore_main_panel()
            self._minimized = False
        else:
            self._collapse_main_panel()
            self._minimized = True
        self._update_minimize_button()

    def _collapse_main_panel(self):
        try:
            self.root.update_idletasks()
        except Exception:
            pass

        width = max(self.root.winfo_width(), 1)
        height = max(self.root.winfo_height(), 1)
        self._normal_size = (width, height)

        cached = []
        for child in self.wrap.winfo_children():
            if child is self.header:
                continue
            try:
                info = child.pack_info()
            except Exception:
                info = None
            if not info:
                continue
            info.pop("in", None)
            info.pop("before", None)
            info.pop("after", None)
            cached.append((child, info))
            try:
                child.pack_forget()
            except Exception:
                pass
        self._minimized_children = cached

        try:
            self.root.update_idletasks()
            header_height = self.header.winfo_reqheight()
            try:
                pad = int(HEADER_PADY)
            except Exception:
                pad = 0
            total_height = header_height + (pad * 2) + 6
            total_height = max(total_height, header_height + 4)
            x = self.root.winfo_x()
            y = self.root.winfo_y()
            width = max(self.root.winfo_width(), 1)
            self.root.geometry(f"{width}x{total_height}+{x}+{y}")
        except Exception:
            pass

    def _restore_main_panel(self):
        for child, info in self._minimized_children:
            try:
                child.pack(**info)
            except Exception:
                try:
                    child.pack()
                except Exception:
                    pass
        self._minimized_children = []
        try:
            self._ensure_hint_layout()
        except Exception:
            pass

        try:
            self.root.update_idletasks()
            x = self.root.winfo_x()
            y = self.root.winfo_y()
            if self._normal_size:
                width, height = self._normal_size
            else:
                width, height = self.root.winfo_width(), self.root.winfo_height()
            width = max(width, 1)
            height = max(height, 1)
            self.root.geometry(f"{width}x{height}+{x}+{y}")
        except Exception:
            pass

    def _update_minimize_button(self):
        try:
            if self._minimized:
                self.minimize_btn.configure(text="[]")
            else:
                self.minimize_btn.configure(text="_")
        except Exception:
            pass

    def _build_config_toggles(self):
        try:
            for btn in self._config_buttons:
                try:
                    btn.destroy()
                except Exception:
                    pass
        except Exception:
            pass
        self._config_buttons = []
        for idx in range(len(self._config_states)):
            btn = ctk.CTkButton(
                self.config_toggle_frame,
                text="",
                width=14,
                height=14,
                corner_radius=3,
                fg_color="#1b1f24",
                hover_color="#34495e",
                border_width=2,
                border_color="#3f3f46",
                command=lambda i=idx: self._toggle_config_slot(i),
            )
            btn.pack(side="left", padx=4)
            self._config_buttons.append(btn)
        self._refresh_all_config_buttons()

    def _toggle_config_slot(self, index: int):
        if not (0 <= index < len(self._config_states)):
            return

        state = int(self._config_states[index])
        if state == 2:
            self._config_states[index] = 0
            if self._config_active == index:
                self._config_active = None
                fallback = self._find_config_candidate(exclude=index)
                if fallback is not None:
                    self._set_active_config(fallback)
        elif state == 0:
            self._config_states[index] = 1
        else:  # state == 1
            self._set_active_config(index)

        self._refresh_all_config_buttons()
        self._save_settings()

    def _set_active_config(self, index: int | None):
        if index is None:
            self._config_active = None
            return
        if not (0 <= index < len(self._config_states)):
            return
        prev = self._config_active
        if prev is not None and 0 <= prev < len(self._config_states):
            if self._config_states[prev] == 2 and prev != index:
                self._config_states[prev] = 1
        self._config_active = index
        self._config_states[index] = 2

    def _find_config_candidate(self, exclude: int | None = None):
        for idx, state in enumerate(self._config_states):
            if idx == exclude:
                continue
            if state == 2:
                return idx
        for idx, state in enumerate(self._config_states):
            if idx == exclude:
                continue
            if state == 1:
                return idx
        return None

    def _resolve_target_config(self, explicit: int | None = None):
        if explicit is not None:
            try:
                idx = int(explicit)
            except Exception:
                idx = 0
            if idx < 0:
                idx = 0
            if len(self._config_states) == 0:
                self._config_states = [2] + [0] * 3
            if idx >= len(self._config_states):
                idx = len(self._config_states) - 1
            return idx

        if self._config_active is not None and 0 <= self._config_active < len(
            self._config_states
        ):
            if self._config_states[self._config_active] == 2:
                return self._config_active

        candidate = self._find_config_candidate()
        if candidate is not None:
            if self._config_states[candidate] != 2:
                self._set_active_config(candidate)
                self._refresh_all_config_buttons()
            return self._config_active if self._config_active is not None else candidate

        if not self._config_states:
            self._config_states = [2] + [0] * 3
        self._config_states[0] = 2
        self._config_active = 0
        self._refresh_all_config_buttons()
        return 0

    def _refresh_all_config_buttons(self):
        for idx in range(len(self._config_states)):
            self._refresh_config_button(idx)
        self._apply_config_visibility()

    def _refresh_config_button(self, index: int):
        buttons = getattr(self, "_config_buttons", [])
        if not (0 <= index < len(buttons)):
            return
        btn = buttons[index]
        state = int(self._config_states[index])
        try:
            if state == 2:
                btn.configure(fg_color="#1f6aa5",
                              hover_color="#155a8a", border_width=0)
            elif state == 1:
                btn.configure(fg_color="#2ecc71",
                              hover_color="#27ae60", border_width=0)
            else:
                btn.configure(
                    fg_color="#1b1f24",
                    hover_color="#34495e",
                    border_width=2,
                    border_color="#3f3f46",
                )
        except Exception:
            pass

    def _apply_config_visibility(self):
        modules = getattr(self, "_modules", {}) or {}
        for mod_id, module in list(modules.items()):
            cfg_idx = int(module.get("config", 0) or 0)
            if cfg_idx < 0 or cfg_idx >= len(self._config_states):
                cfg_idx = 0
            module["config"] = cfg_idx
            state = int(self._config_states[cfg_idx])
            win = module.get("win")
            if not win:
                continue
            try:
                exists = win.winfo_exists() == 1
            except Exception:
                exists = False
            if not exists:
                continue
            try:
                if state == 0:
                    win.withdraw()
                    module["visible"] = False
                else:
                    win.deiconify()
                    try:
                        win.lift()
                    except Exception:
                        pass
                    module["visible"] = True
            except Exception:
                pass

    def _stop_all_scrolls(self, exclude=None):
        new_list = []
        for btn in getattr(self, "_scroll_buttons", []):
            try:
                if not btn or btn.winfo_exists() != 1:
                    continue
            except Exception:
                continue
            if exclude is not None and btn is exclude:
                new_list.append(btn)
                continue
            try:
                btn._stop_flag = True
                btn._scrolling = False
            except Exception:
                pass
            new_list.append(btn)
        self._scroll_buttons = new_list

    def _prepare_hover_hint(self, widget, hint_text):
        if not hint_text or not hasattr(self, "hint"):
            return (lambda: None, lambda: None)

        def show():
            try:
                if getattr(self, "_hover_hint_owner", None) is None:
                    self._hover_hint_backup = self.hint.cget("text")
            except Exception:
                if getattr(self, "_hover_hint_owner", None) is None:
                    self._hover_hint_backup = ""
            self._hover_hint_owner = widget
            try:
                self.hint.configure(text=hint_text)
            except Exception:
                pass

        def clear():
            if getattr(self, "_hover_hint_owner", None) is not widget:
                return
            try:
                current = self.hint.cget("text")
            except Exception:
                current = ""
            if current == hint_text:
                try:
                    self.hint.configure(text=self._hover_hint_backup)
                except Exception:
                    pass
            self._hover_hint_owner = None
            self._hover_hint_backup = ""

        return show, clear

    def _preload_icons(self, keys):
        try:
            iterable = list(keys)
        except TypeError:
            iterable = [keys]
        for key in iterable:
            try:
                self._resolve_button_icon(key)
            except Exception:
                pass

    def _apply_pending_icon_updates(self):
        keys = getattr(self, "_pending_icon_updates", None)
        if not keys:
            return
        try:
            keys = list(keys)
        except Exception:
            keys = list(set(keys))
        remaining = set()
        for key in keys:
            icon = self._resolve_button_icon(key)
            entries = self._extension_buttons.get(key, [])
            if not entries:
                remaining.add(key)
                continue
            if not icon:
                remaining.add(key)
                continue
            log.info("[ICON] apply %s -> %d button(s)", key, len(entries))
            for btn, _defaults in entries:
                try:
                    if not btn or btn.winfo_exists() != 1:
                        continue
                    btn.configure(text="", image=icon, compound="center")
                    btn._icon_image = icon
                    try:
                        existing_label = getattr(btn, "_icon_label", None)
                    except Exception:
                        existing_label = None
                    if (
                        existing_label
                        and getattr(existing_label, "winfo_exists", lambda: 0)()
                    ):
                        try:
                            existing_label.destroy()
                        except Exception:
                            pass
                    enter_cb = getattr(btn, "_icon_enter_cb", None)
                    leave_cb = getattr(btn, "_icon_leave_cb", None)
                    click_cb = getattr(btn, "_icon_click_cb", None)
                    label = self._create_icon_overlay(
                        btn, icon, enter_cb, leave_cb, click_cb
                    )
                    if label is None:
                        btn._icon_label = None
                    else:
                        btn._icon_label = label
                    try:
                        btn.update_idletasks()
                    except Exception:
                        pass
                except Exception:
                    continue
        self._pending_icon_updates = remaining
        if remaining:
            try:
                self.root.after(200, self._apply_pending_icon_updates)
            except Exception:
                pass

    def _resolve_button_icon(self, key):
        if not key:
            return None
        cache_key = "".join(
            ch.lower() for ch in str(key) if ch.isalnum() or ch in ("-", "_")
        )
        if not cache_key:
            return None
        cache = getattr(self, "_icon_cache", None)
        if cache is None:
            return None
        if cache_key in cache:
            return cache[cache_key]
        root = getattr(self, "_icon_root", None)
        if not root or not root.exists():
            cache[cache_key] = None
            return None
        svg_path = root / f"{cache_key}.svg"
        if not svg_path.exists():
            cache[cache_key] = None
            return None
        icon = self._render_svg_icon(svg_path)
        cache[cache_key] = icon
        return icon

    def _render_svg_icon(self, svg_path):
        size = max(10, int(min(BTN_W, BTN_H) * 0.55))
        image = None
        try:
            import cairosvg

            png_bytes = cairosvg.svg2png(
                url=str(svg_path),
                output_width=size,
                output_height=size,
            )
            image = Image.open(io.BytesIO(png_bytes)).convert("RGBA")
        except Exception as exc:
            if not getattr(self, "_svg_warning_emitted", False):
                log.warning(
                    (
                        "SVG icons: Cairo renderer unavailable (%s). "
                        "Falling back to built-in rasterizer."
                    ),
                    exc,
                )
                self._svg_warning_emitted = True
            image = self._rasterize_svg_basic(svg_path, size)
        if image is None:
            return None
        try:
            debug_dir = getattr(self, "_icon_debug_dir", None)
            if debug_dir is None:
                debug_dir = Path.cwd() / "tmp"
                self._icon_debug_dir = debug_dir
            debug_dir.mkdir(parents=True, exist_ok=True)
            image.save(debug_dir / f"{svg_path.stem}_icon.png")
        except Exception:
            pass
        return ctk.CTkImage(light_image=image, dark_image=image, size=(size, size))

    def _create_icon_overlay(
        self, button, icon, on_enter=None, on_leave=None, on_click=None
    ):
        if not button or not icon:
            return None
        try:
            overlay = ctk.CTkLabel(button, text="", image=icon)
            overlay.place(relx=0.0, rely=0.0, anchor="nw",
                          relwidth=1.0, relheight=1.0)
            bindings = (
                ("<Enter>", on_enter),
                ("<Leave>", on_leave),
                ("<Button-1>", on_click),
            )
            for sequence, handler in bindings:
                if handler:
                    try:
                        overlay.bind(sequence, handler, add="+")
                    except Exception:
                        pass
            return overlay
        except Exception:
            return None

    def _rasterize_svg_basic(self, svg_path, size):
        try:
            from svg.path import parse_path, Move, Close
        except Exception as exc:
            if not getattr(self, "_svg_fallback_warning_emitted", False):
                log.warning(
                    "SVG fallback rasterizer requires svg.path (pip install svg.path). (%s)",
                    exc,
                )
                self._svg_fallback_warning_emitted = True
            return None
        try:
            import xml.etree.ElementTree as ET

            tree = ET.parse(svg_path)
            root = tree.getroot()
        except Exception as exc:
            log.warning("Failed to parse SVG %s: %s", svg_path.name, exc)
            return None

        def _split_numbers(value, default):
            if value is None:
                return default
            parts = []
            for chunk in value.replace(",", " ").split():
                if not chunk:
                    continue
                try:
                    parts.append(float(chunk))
                except Exception:
                    parts.append(0.0)
            return parts if parts else default

        view_box = root.attrib.get("viewBox")
        if view_box:
            vb = _split_numbers(view_box, [0.0, 0.0, 24.0, 24.0])
            if len(vb) < 4:
                vb += [24.0] * (4 - len(vb))
            vx, vy, vw, vh = vb[:4]
        else:
            vx = float(root.attrib.get("x", "0") or 0.0)
            vy = float(root.attrib.get("y", "0") or 0.0)
            vw = float(root.attrib.get("width", "24") or 24.0)
            vh = float(root.attrib.get("height", "24") or 24.0)

        span = max(vw, vh, 1.0)
        scale = size / span

        def transform_point(px, py):
            return ((px - vx) * scale, (py - vy) * scale)

        def parse_color(value, fallback):
            if not value or value == "none":
                return None
            if value == "currentColor":
                return fallback
            value = value.strip()
            if value.startswith("#"):
                hex_value = value[1:]
                if len(hex_value) == 3:
                    hex_value = "".join(ch * 2 for ch in hex_value)
                if len(hex_value) == 6:
                    try:
                        r = int(hex_value[0:2], 16)
                        g = int(hex_value[2:4], 16)
                        b = int(hex_value[4:6], 16)
                        return (r, g, b, 255)
                    except Exception:
                        return fallback
            return fallback

        def parse_style(style_value):
            if not style_value:
                return {}
            result = {}
            for part in style_value.split(";"):
                if ":" not in part:
                    continue
                key, val = part.split(":", 1)
                result[key.strip()] = val.strip()
            return result

        image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)
        default_color = (255, 255, 255, 255)

        def render_element(elem, inherited):
            attrs = dict(inherited)
            attrs.update(elem.attrib)
            if "style" in attrs:
                attrs.update(parse_style(attrs.pop("style")))
            tag = elem.tag.rsplit("}", 1)[-1]
            if tag == "g":
                for child in list(elem):
                    render_element(child, attrs)
                return
            stroke = parse_color(
                attrs.get("stroke"), parse_color(
                    inherited.get("stroke"), default_color)
            )
            stroke_width_attr = attrs.get(
                "stroke-width",
                inherited.get("stroke-width",
                              root.attrib.get("stroke-width", "2")),
            )
            try:
                stroke_width = float(stroke_width_attr)
            except Exception:
                stroke_width = 2.0
            stroke_px = max(2, int(round(stroke_width * scale)))

            if tag == "rect":
                x = float(attrs.get("x", 0.0) or 0.0)
                y = float(attrs.get("y", 0.0) or 0.0)
                w = float(attrs.get("width", 0.0) or 0.0)
                h = float(attrs.get("height", 0.0) or 0.0)
                rx_val = attrs.get("rx") or attrs.get("ry") or 0.0
                try:
                    rx = float(rx_val)
                except Exception:
                    rx = 0.0
                x0, y0 = transform_point(x, y)
                x1, y1 = transform_point(x + w, y + h)
                bbox = [x0, y0, x1, y1]
                radius = max(0, int(round(rx * scale)))
                if radius > 0:
                    draw.rounded_rectangle(
                        bbox, radius=radius, outline=stroke, width=stroke_px
                    )
                else:
                    draw.rectangle(bbox, outline=stroke, width=stroke_px)
                return

            if tag == "line":
                x1 = float(attrs.get("x1", 0.0) or 0.0)
                y1 = float(attrs.get("y1", 0.0) or 0.0)
                x2 = float(attrs.get("x2", 0.0) or 0.0)
                y2 = float(attrs.get("y2", 0.0) or 0.0)
                draw.line(
                    (*transform_point(x1, y1), *transform_point(x2, y2)),
                    fill=stroke,
                    width=stroke_px,
                    joint="curve",
                )
                return

            if tag == "circle":
                cx = float(attrs.get("cx", 0.0) or 0.0)
                cy = float(attrs.get("cy", 0.0) or 0.0)
                r = float(attrs.get("r", 0.0) or 0.0)
                x0, y0 = transform_point(cx - r, cy - r)
                x1, y1 = transform_point(cx + r, cy + r)
                draw.ellipse([x0, y0, x1, y1], outline=stroke, width=stroke_px)
                return

            if tag in {"polyline", "polygon"}:
                points_attr = attrs.get("points", "")
                if not points_attr:
                    return
                coords = _split_numbers(points_attr, [])
                pts = []
                for i in range(0, len(coords), 2):
                    px = coords[i]
                    py = coords[i + 1] if i + 1 < len(coords) else 0.0
                    pts.append(transform_point(px, py))
                if tag == "polygon" and pts:
                    pts.append(pts[0])
                if len(pts) > 1:
                    draw.line(pts, fill=stroke, width=stroke_px, joint="curve")
                return

            if tag == "path":
                d = attrs.get("d")
                if not d:
                    return
                try:
                    path = parse_path(d)
                except Exception:
                    return
                current = []
                start_point = None

                def to_point(complex_point):
                    return transform_point(complex_point.real, complex_point.imag)

                for segment in path:
                    if isinstance(segment, Move):
                        if len(current) > 1:
                            draw.line(
                                current, fill=stroke, width=stroke_px, joint="curve"
                            )
                        current = [to_point(segment.end)]
                        start_point = current[0]
                        continue
                    if isinstance(segment, Close):
                        if start_point is not None:
                            current.append(start_point)
                        if len(current) > 1:
                            draw.line(
                                current, fill=stroke, width=stroke_px, joint="curve"
                            )
                        current = []
                        start_point = None
                        continue

                    try:
                        seg_length = segment.length(error=1e-3)
                    except Exception:
                        seg_length = 1.0
                    steps = max(2, int(seg_length * scale / 1.5))
                    steps = min(steps, 96)
                    samples = []
                    for i in range(1, steps + 1):
                        t = i / steps
                        pt = segment.point(t)
                        samples.append(to_point(pt))
                    if not current:
                        start = to_point(segment.point(0))
                        current = [start]
                    current.extend(samples)

                if len(current) > 1:
                    draw.line(current, fill=stroke,
                              width=stroke_px, joint="curve")
                return

            # Unsupported element types are ignored silently.

        inherited_defaults = {
            "stroke": root.attrib.get("stroke", "currentColor"),
            "stroke-width": root.attrib.get("stroke-width", "2"),
        }
        for child in list(root):
            render_element(child, inherited_defaults)

        return image

    def _register_extension_button(self, key, button):
        if not key:
            return
        defaults = {}
        for opt in (
            "fg_color",
            "hover_color",
            "text_color",
            "border_color",
            "border_width",
        ):
            try:
                defaults[opt] = button.cget(opt)
            except Exception:
                defaults[opt] = None
        entries = []
        for existing_btn, existing_defaults in self._extension_buttons.get(key, []):
            try:
                if existing_btn and existing_btn.winfo_exists():
                    entries.append((existing_btn, existing_defaults))
            except Exception:
                continue
        entries.append((button, defaults))
        self._extension_buttons[key] = entries
        try:
            log.info("[ICON] register button %s (total=%d)", key, len(entries))
        except Exception:
            pass
        if key in self._highlighted_extensions:
            self._apply_highlight_style(button, defaults)

    def _update_button_icon(self, button, icon):
        if not button:
            return
        try:
            if icon:
                button.configure(image=icon, compound="center")
        except Exception:
            pass
        try:
            overlay = getattr(button, "_icon_label", None)
            if overlay and getattr(overlay, "winfo_exists", lambda: 0)():
                overlay.configure(image=icon)
        except Exception:
            pass

    def _make_tinted_icon(self, icon, color):
        if not icon:
            return None
        try:
            base = getattr(icon, "_light_image", None)
            size = getattr(icon, "_size", None)
            if base is None or size is None:
                return None
            rgba = ImageColor.getcolor(color, "RGB")
            tint = Image.new("RGBA", base.size, (*rgba, 255))
            alpha = base.split()[-1] if base.mode in ("RGBA", "LA") else None
            if alpha is not None:
                tint.putalpha(alpha)
            else:
                tint.putalpha(255)
            return ctk.CTkImage(light_image=tint, dark_image=tint, size=size)
        except Exception:
            return None

    def _apply_highlight_style(self, button, defaults=None):
        try:
            has_icon = bool(getattr(button, "_icon_image", None))
            if has_icon:
                highlight_icon = getattr(button, "_icon_image_highlight", None)
                if highlight_icon is None:
                    base_icon = getattr(button, "_icon_image", None)
                    highlight_icon = self._make_tinted_icon(
                        base_icon, "#1f6aa5")
                    try:
                        button._icon_image_highlight = highlight_icon
                    except Exception:
                        pass
                if highlight_icon:
                    self._update_button_icon(button, highlight_icon)
                fg = None
                hover = None
                if isinstance(defaults, dict):
                    fg = defaults.get("fg_color")
                    hover = defaults.get("hover_color")
                kwargs = {
                    "border_color": ("#1f6aa5", "#1f6aa5"),
                    "border_width": 2,
                }
                if fg not in (None, ""):
                    kwargs["fg_color"] = fg
                if hover not in (None, ""):
                    kwargs["hover_color"] = hover
                button.configure(**kwargs)
            else:
                button.configure(
                    fg_color=("#ffffff", "#ffffff"),
                    hover_color=("#f0f0f0", "#f0f0f0"),
                    text_color=("#1f6aa5", "#1f6aa5"),
                    border_color=("#1f6aa5", "#1f6aa5"),
                    border_width=2,
                )
        except Exception:
            pass

    def _restore_button_style(self, button, defaults):
        try:
            kwargs = {}
            for key, value in defaults.items():
                if value in (None, ""):
                    continue
                kwargs[key] = value
            if kwargs:
                button.configure(**kwargs)
            if getattr(button, "_icon_image", None):
                self._update_button_icon(
                    button, getattr(button, "_icon_image"))
        except Exception:
            pass

    def _set_extension_highlight(self, key, active):
        if not key:
            return
        entries = self._extension_buttons.get(key, [])
        kept = []
        for btn, defaults in entries:
            try:
                if not btn or btn.winfo_exists() != 1:
                    continue
            except Exception:
                continue
            if active:
                self._apply_highlight_style(btn, defaults)
            else:
                self._restore_button_style(btn, defaults)
            kept.append((btn, defaults))
        if kept:
            self._extension_buttons[key] = kept
        else:
            self._extension_buttons.pop(key, None)
        if active:
            self._highlighted_extensions.add(key)
        else:
            self._highlighted_extensions.discard(key)

    def _attach_extension_hover(self, widget, show_fn, clear_fn):
        def _on_enter(_):
            try:
                show_fn()
            except Exception:
                pass
            try:
                self._enter_extension_hover()
            except Exception:
                pass

        def _on_leave(_):
            try:
                clear_fn()
            except Exception:
                pass
            try:
                self._exit_extension_hover()
            except Exception:
                pass

        try:
            widget.bind("<Enter>", _on_enter, add="+")
            widget.bind("<Leave>", _on_leave, add="+")
        except Exception:
            pass

    def _enter_extension_hover(self):
        try:
            if getattr(self, "_in_extension_hover", False):
                return
            self._in_extension_hover = True
            self._hover_restore_delay = getattr(
                self, "dwell_delay", DWELL_DELAY_INIT)
            try:
                self._hover_restore_color = self.bar.cget("progress_color")
            except Exception:
                self._hover_restore_color = BAR_DEFAULT
            self.dwell_delay = max(
                3.0, self._hover_restore_delay or DWELL_DELAY_INIT)
            try:
                self.bar.configure(progress_color=BAR_OK)
            except Exception:
                pass
        except Exception:
            pass

    def _exit_extension_hover(self):
        try:
            if not getattr(self, "_in_extension_hover", False):
                return
            self._in_extension_hover = False
            restore_delay = getattr(
                self, "_hover_restore_delay", DWELL_DELAY_INIT)
            self.dwell_delay = restore_delay if restore_delay else DWELL_DELAY_INIT
            color = getattr(self, "_hover_restore_color", BAR_DEFAULT)
            try:
                self.bar.configure(progress_color=color)
            except Exception:
                try:
                    self.bar.configure(progress_color=BAR_DEFAULT)
                except Exception:
                    pass
        except Exception:
            pass

    def _make_dwell_button(
        self,
        parent,
        label,
        command,
        hint_text=None,
        ext_key=None,
        hover_mode="extension",
    ):
        icon = None
        for candidate in (ext_key, label):
            icon = self._resolve_button_icon(candidate)
            if icon:
                break
        has_icon = icon is not None
        btn_kwargs = {
            "width": BTN_W,
            "height": BTN_H,
            "corner_radius": BTN_CORNER,
            "font": BTN_FONT,
        }
        if has_icon:
            btn_kwargs["text"] = ""
            btn_kwargs["image"] = icon
            btn_kwargs["compound"] = "center"
        else:
            btn_kwargs["text"] = label
        btn = ctk.CTkButton(parent, **btn_kwargs)
        btn._icon_label = None
        btn._icon_enter_cb = None
        btn._icon_leave_cb = None
        btn._icon_click_cb = None
        if has_icon:
            btn._icon_image = icon
        else:
            btn._icon_image = None
            pending = getattr(self, "_pending_icon_updates", None)
            if isinstance(pending, set) and ext_key:
                pending.add(ext_key)
        btn._after = None
        btn._hover_hint = hint_text
        show_hint, clear_hint = self._prepare_hover_hint(btn, hint_text)

        if ext_key:
            self._register_extension_button(ext_key, btn)
            pending = getattr(self, "_pending_icon_updates", None)
            if isinstance(pending, set):
                schedule = len(pending) == 0
                pending.add(ext_key)
                if schedule:
                    try:
                        self.root.after_idle(self._apply_pending_icon_updates)
                    except Exception:
                        pass

        def _run_command():
            try:
                btn._after = None
            except Exception:
                pass
            if callable(command):
                command()

        def on_enter(_):
            if getattr(self, "_suspend_dwell_actions", 0) > 0 or self.drg_mode:
                btn._after = None
                return
            if hover_mode == "instant":
                _run_command()
                return
            if hover_mode != "extension":
                return
            show_hint()
            try:
                self._enter_extension_hover()
            except Exception:
                pass
            btn._after = self.root.after(550, _run_command)

        def on_leave(_):
            if hover_mode != "extension":
                return
            if btn._after:
                self.root.after_cancel(btn._after)
                btn._after = None
            clear_hint()
            try:
                self._exit_extension_hover()
            except Exception:
                pass

        def on_click(_):
            try:
                if btn._after:
                    self.root.after_cancel(btn._after)
                    btn._after = None
            except Exception:
                pass
            if hover_mode == "extension":
                show_hint()
                try:
                    self._enter_extension_hover()
                except Exception:
                    pass
            _run_command()

        btn.bind("<Enter>", on_enter)
        btn.bind("<Leave>", on_leave)
        try:
            btn.bind("<Button-1>", on_click, add="+")
        except Exception:
            pass
        btn._icon_enter_cb = on_enter
        btn._icon_leave_cb = on_leave
        btn._icon_click_cb = on_click
        if has_icon:
            label = self._create_icon_overlay(
                btn, icon, on_enter, on_leave, on_click)
            if label is None:
                btn._icon_label = None
            else:
                btn._icon_label = label
        btn.pack(side="left", padx=4, pady=0)
        return btn

    def _make_scroll_button(self, parent, label, direction: str, hint_text=None):
        btn = ctk.CTkButton(
            parent,
            text=label,
            width=BTN_W,
            height=BTN_H,
            corner_radius=BTN_CORNER,
            font=BTN_FONT,
        )
        btn._scrolling = False
        btn._stop_flag = False
        btn._hover_hint = hint_text
        show_hint, clear_hint = self._prepare_hover_hint(btn, hint_text)

        def _loop():
            step = SCROLL_STEP if direction == "up" else -SCROLL_STEP
            while not btn._stop_flag and btn._scrolling:
                try:
                    if not self._ensure_scroll_target():
                        time.sleep(0.12)
                        continue
                    if not self._emit_scroll(step):
                        if not self._force_scroll_message(step):
                            pyautogui.scroll(step)
                except Exception:
                    pass
                try:
                    time.sleep(float(SCROLL_INTERVAL))
                except Exception:
                    time.sleep(0.08)

        def on_enter(_):
            if getattr(self, "_suspend_dwell_actions", 0) > 0 or self.drg_mode:
                return
            try:
                self._ensure_scroll_target()
            except Exception:
                pass
            show_hint()
            try:
                self._enter_extension_hover()
            except Exception:
                pass
            self._stop_all_scrolls()
            btn._stop_flag = False
            btn._scrolling = True
            threading.Thread(target=_loop, daemon=True).start()

        def on_leave(_):
            btn._stop_flag = True
            btn._scrolling = False
            self._stop_all_scrolls()
            clear_hint()
            try:
                self._exit_extension_hover()
            except Exception:
                pass

        btn.bind("<Enter>", on_enter)
        btn.bind("<Leave>", on_leave)
        btn.pack(side="left", padx=4, pady=0)
        try:
            self._scroll_buttons.append(btn)
        except Exception:
            pass
        return btn

    def _layout_shelf_buttons(self, container, buttons):
        if not buttons:
            return
        if not hasattr(container, "after_idle"):
            return

        def _perform_layout():
            try:
                container._layout_pending = False
            except Exception:
                pass
            try:
                if not container.winfo_exists():
                    return
            except Exception:
                return
            for child in list(container.winfo_children()):
                try:
                    child.grid_forget()
                except Exception:
                    pass
            try:
                container.grid_propagate(False)
            except Exception:
                pass

            pad_x = 4
            pad_y = 4
            cell_w = SHELF_BTN_W + pad_x * 2

            try:
                container.update_idletasks()
            except Exception:
                pass
            try:
                self.root.update_idletasks()
            except Exception:
                pass

            try:
                available = int(container.winfo_width())
            except Exception:
                available = 0
            if available <= cell_w:
                try:
                    available = int(self.root.winfo_width()) - 2 * (8 + 6)
                except Exception:
                    available = cell_w
            available = max(cell_w, available)
            cols = max(1, available // cell_w)

            for col in range(cols + 3):
                try:
                    container.grid_columnconfigure(col, weight=0)
                except Exception:
                    pass

            alive = [b for b in buttons if getattr(
                b, "winfo_exists", lambda: 0)() == 1]
            for index, btn in enumerate(alive):
                row, col = divmod(index, cols)
                try:
                    btn.grid(row=row, column=col, padx=pad_x,
                             pady=pad_y, sticky="n")
                except Exception:
                    pass

            try:
                container.update_idletasks()
            except Exception:
                pass

            # Compute actual cell height from button requests to avoid leftover slack
            btn_req_h = SHELF_BTN_H
            for b in alive:
                try:
                    btn_req_h = max(btn_req_h, int(b.winfo_reqheight()))
                except Exception:
                    pass

            rows = max(1, (len(alive) + cols - 1) // cols)
            cell_h = btn_req_h + pad_y * 2
            total_h = rows * cell_h

            pad_top = (
                SHELF_PADY[0]
                if isinstance(SHELF_PADY, (tuple, list))
                else (SHELF_PADY or 0)
            )
            pad_bottom = (
                SHELF_PADY[1]
                if isinstance(SHELF_PADY, (tuple, list))
                else (SHELF_PADY or 0)
            )
            row_height = max(0, total_h + pad_top + pad_bottom)

            row_frame = getattr(container, "master", None)
            if row_frame is not None:
                try:
                    row_frame.pack_propagate(False)
                except Exception:
                    pass
                try:
                    row_frame.configure(height=row_height)
                except Exception:
                    pass
            self._current_shelf_height = row_height
            try:
                self._resize_root_height()
            except Exception:
                pass

        try:
            if getattr(container, "_layout_pending", False):
                return
            container._layout_pending = True
            container.after_idle(_perform_layout)
        except Exception:
            _perform_layout()

    def _is_point_inside_hud(self, pos):
        try:
            rx = int(self.root.winfo_rootx())
            ry = int(self.root.winfo_rooty())
            rw = int(self.root.winfo_width())
            rh = int(self.root.winfo_height())
        except Exception:
            return False
        if rw <= 0 or rh <= 0:
            return False
        return rx <= pos[0] <= rx + rw and ry <= pos[1] <= ry + rh

    def _window_from_point(self, pos):
        try:
            point = wintypes.POINT(int(pos[0]), int(pos[1]))
            return ctypes.windll.user32.WindowFromPoint(point)
        except Exception:
            return None

    def _is_window_valid(self, hwnd):
        try:
            return bool(hwnd) and bool(ctypes.windll.user32.IsWindow(hwnd))
        except Exception:
            return False

    def _register_hud_window(self, hwnd):
        try:
            if not hwnd:
                return
            value = int(hwnd)
        except Exception:
            return
        if not hasattr(self, "_hud_windows"):
            self._hud_windows = set()
        self._hud_windows.add(value)

    def _unregister_hud_window(self, hwnd):
        try:
            if not hwnd:
                return
            value = int(hwnd)
        except Exception:
            return
        try:
            windows = getattr(self, "_hud_windows", None)
        except Exception:
            windows = None
        if isinstance(windows, set):
            windows.discard(value)

    def _set_clipboard_text(self, text: str):
        if text is None:
            return False
        try:
            self.root.clipboard_clear()
            self.root.clipboard_append(text)
            return True
        except Exception:
            return False

    def _is_our_window(self, hwnd):
        try:
            if not hwnd:
                return False
            value = int(hwnd)
        except Exception:
            return False
        try:
            windows = getattr(self, "_hud_windows", None)
        except Exception:
            windows = None
        if windows and value in windows:
            return True
        try:
            user32 = ctypes.windll.user32
        except Exception:
            return False
        if not windows:
            root = getattr(self, "_hud_hwnd", None)
            if root:
                windows = {int(root)}
        if not windows:
            return False
        for base in list(windows):
            if not base or base == value:
                continue
            try:
                if user32.IsChild(base, value):
                    return True
            except Exception:
                continue
        return False

    def _update_scroll_target(self, pos):
        if not isinstance(pos, tuple) or len(pos) != 2:
            return
        try:
            inside = self._is_point_inside_hud(pos)
        except Exception:
            inside = False
        if inside:
            return
        hwnd = self._window_from_point(pos)
        if not self._is_window_valid(hwnd) or self._is_our_window(hwnd):
            return
        prev_hwnd = getattr(self, "_scroll_target_hwnd", None)
        prev_point = getattr(self, "_scroll_target_point", None)
        px, py = int(pos[0]), int(pos[1])
        self._last_outside_point = (px, py)
        self._last_outside_hwnd = hwnd
        self._scroll_target_hwnd = hwnd
        self._scroll_target_point = (px, py)

    def _post_scroll_message(self, hwnd, clicks, x, y):
        if not self._is_window_valid(hwnd):
            return False
        delta = int(clicks) * WHEEL_DELTA
        if delta == 0:
            return False
        try:
            wparam = ctypes.c_int(delta << 16).value
            lparam = ctypes.c_int(((int(y) & 0xFFFF) << 16)
                                  | (int(x) & 0xFFFF)).value
        except Exception:
            return False
        try:
            user32 = ctypes.windll.user32
            result = ctypes.c_ulong()
            visited = set()
            current = hwnd
            while current and current not in visited:
                visited.add(current)
                if user32.SendMessageTimeoutW(
                    current,
                    WM_MOUSEWHEEL,
                    wparam,
                    lparam,
                    SMTO_ABORTIFHUNG | SMTO_NORMAL,
                    20,
                    ctypes.byref(result),
                ):
                    return True
                current = user32.GetParent(current)
            ancestor = user32.GetAncestor(hwnd, GA_ROOT)
            if ancestor and ancestor not in visited:
                if user32.SendMessageTimeoutW(
                    ancestor,
                    WM_MOUSEWHEEL,
                    wparam,
                    lparam,
                    SMTO_ABORTIFHUNG | SMTO_NORMAL,
                    20,
                    ctypes.byref(result),
                ):
                    return True
        except Exception:
            pass
        return False

    def _emit_scroll(self, clicks):
        hwnd = getattr(self, "_scroll_target_hwnd", None)
        point = getattr(self, "_scroll_target_point", None)
        if not hwnd or not point:
            return False
        return self._post_scroll_message(hwnd, clicks, point[0], point[1])

    def _ensure_scroll_target(self):
        try:
            hwnd = getattr(self, "_scroll_target_hwnd", None)
            if self._is_window_valid(hwnd) and not self._is_our_window(hwnd):
                return True
        except Exception:
            pass

        try:
            last_point = getattr(self, "_last_outside_point", None)
            if isinstance(last_point, tuple) and len(last_point) == 2:
                fresh = self._window_from_point(last_point)
                if self._is_window_valid(fresh) and not self._is_our_window(fresh):
                    self._last_outside_hwnd = fresh
                    self._scroll_target_hwnd = fresh
                    self._scroll_target_point = (
                        int(last_point[0]), int(last_point[1]))
                    return True
        except Exception:
            pass

        try:
            last_hwnd = getattr(self, "_last_outside_hwnd", None)
            last_point = getattr(self, "_last_outside_point", None)
            if (
                self._is_window_valid(last_hwnd)
                and not self._is_our_window(last_hwnd)
                and isinstance(last_point, tuple)
                and len(last_point) == 2
            ):
                self._scroll_target_hwnd = last_hwnd
                self._scroll_target_point = (
                    int(last_point[0]), int(last_point[1]))
                return True
        except Exception:
            pass

        try:
            fg = ctypes.windll.user32.GetForegroundWindow()
            if self._is_window_valid(fg) and not self._is_our_window(fg):
                fallback_point = getattr(self, "_last_outside_point", None)
                if not (isinstance(fallback_point, tuple) and len(fallback_point) == 2):
                    px, py = pyautogui.position()
                    fallback_point = (int(px), int(py))
                self._last_outside_hwnd = fg
                self._scroll_target_hwnd = fg
                self._scroll_target_point = (
                    int(fallback_point[0]),
                    int(fallback_point[1]),
                )
                return True
        except Exception:
            pass

        return False

    def _force_scroll_message(self, clicks):
        hwnd = getattr(self, "_scroll_target_hwnd", None)
        point = getattr(self, "_scroll_target_point", None)
        if not self._is_window_valid(hwnd) or not point:
            return False
        delta = int(clicks) * WHEEL_DELTA
        if delta == 0:
            return False
        try:
            user32 = ctypes.windll.user32
            wparam = ctypes.c_int(delta << 16).value
            lparam = ctypes.c_int(
                ((int(point[1]) & 0xFFFF) << 16) | (int(point[0]) & 0xFFFF)
            ).value
            result = ctypes.c_ulong()
            if user32.SendMessageTimeoutW(
                hwnd,
                WM_MOUSEWHEEL,
                wparam,
                lparam,
                SMTO_ABORTIFHUNG | SMTO_NORMAL,
                20,
                ctypes.byref(result),
            ):
                return True
            parent = user32.GetParent(hwnd)
            visited = set()
            while parent and parent not in visited:
                visited.add(parent)
                if user32.SendMessageTimeoutW(
                    parent,
                    WM_MOUSEWHEEL,
                    wparam,
                    lparam,
                    SMTO_ABORTIFHUNG | SMTO_NORMAL,
                    20,
                    ctypes.byref(result),
                ):
                    return True
                parent = user32.GetParent(parent)
            ancestor = user32.GetAncestor(hwnd, GA_ROOT)
            if ancestor and ancestor not in visited:
                if user32.SendMessageTimeoutW(
                    ancestor,
                    WM_MOUSEWHEEL,
                    wparam,
                    lparam,
                    SMTO_ABORTIFHUNG | SMTO_NORMAL,
                    20,
                    ctypes.byref(result),
                ):
                    return True
        except Exception:
            pass
        return False

    def _resize_root_height(self):
        try:
            self.root.update_idletasks()
            cur_w = int(self.root.winfo_width())
            try:
                last_w = int(getattr(self, "_last_width", HUD_W))
            except Exception:
                last_w = HUD_W
            cur_w = max(cur_w, last_w, HUD_W)
            x = int(self.root.winfo_x())
            y = int(self.root.winfo_y())
        except Exception:
            return
        try:
            shelf = max(0, int(getattr(self, "_current_shelf_height", 0) or 0))
        except Exception:
            shelf = 0
        base = getattr(self, "_base_height", None)
        if base is None or base <= 0:
            try:
                req = int(self.root.winfo_reqheight())
                base = max(0, req - shelf)
            except Exception:
                base = 0
            self._base_height = base
        total = max(base + shelf, base)
        if total <= 0:
            try:
                total = int(self.root.winfo_height())
            except Exception:
                return
        try:
            self.root.geometry(f"{cur_w}x{total}+{x}+{y}")
            self._last_width = cur_w
            self._last_shelf_h = shelf
        except Exception:
            pass

    def _ensure_hint_layout(self):
        """Keep hint label between the toolbar and the progress bar after layout changes."""
        hint = getattr(self, "hint", None)
        toolbar = getattr(self, "toolbar_row", None)
        bar = getattr(self, "bar", None)
        if not hint or not toolbar:
            return
        try:
            toolbar_mgr = toolbar.winfo_manager()
        except Exception:
            toolbar_mgr = ""
        if toolbar_mgr != "pack":
            try:
                toolbar.pack(side="top", padx=8, pady=ROW_PADY)
            except Exception:
                return
        try:
            if bar and bar.winfo_manager() == "pack":
                try:
                    if hint.winfo_manager() == "pack":
                        hint.pack_configure(before=bar)
                    else:
                        hint.pack(side="top", padx=6,
                                  pady=HINT_PADY, before=bar)
                except Exception:
                    try:
                        hint.pack_forget()
                        hint.pack(side="top", padx=6,
                                  pady=HINT_PADY, before=bar)
                    except Exception:
                        pass
            else:
                try:
                    if hint.winfo_manager() == "pack":
                        hint.pack_configure(after=toolbar)
                    else:
                        hint.pack(side="top", padx=6,
                                  pady=HINT_PADY, after=toolbar)
                except Exception:
                    try:
                        hint.pack_forget()
                        hint.pack(side="top", padx=6, pady=HINT_PADY)
                    except Exception:
                        pass
            if hint.winfo_manager() == "pack":
                try:
                    toolbar.pack_configure(before=hint)
                except Exception:
                    pass
        except Exception:
            pass

    def _refresh_base_height(self):
        try:
            self.root.update_idletasks()
            shelf = max(0, int(getattr(self, "_current_shelf_height", 0) or 0))
            req = int(self.root.winfo_reqheight())
            base = req - shelf
            if base <= 0:
                base = req
            if base <= 0:
                return
            self._base_height = base
            self._resize_root_height()
        except Exception:
            pass

    def _ensure_unique_active_extensions(self):
        uniq = []
        seen = set()
        for key in getattr(self, "active_extensions", []) or []:
            if key in seen:
                continue
            if key not in self._extensions:
                continue
            seen.add(key)
            uniq.append(key)
        self.active_extensions = uniq

    # ----- Extensions toolbar & shelf -----
    def _save_settings(self):
        self._ensure_unique_active_extensions()
        try:
            self._settings["active_extensions"] = list(self.active_extensions)
            # New format: modules with multiple keys
            modules_out = []
            try:
                for mod_id, m in (getattr(self, "_modules", {}) or {}).items():
                    w = m.get("win")
                    keys = list(m.get("keys") or [])
                    if not w or not keys:
                        continue
                    modules_out.append(
                        {
                            "x": int(w.winfo_x()),
                            "y": int(w.winfo_y()),
                            "keys": keys,
                            "orient": m.get("orient", "h"),
                            "config": int(m.get("config", 0) or 0),
                        }
                    )
            except Exception:
                pass
            self._settings["floating_modules"] = modules_out
            # Legacy singletons for backward compatibility
            floats = []
            try:
                for m in modules_out:
                    for k in m.get("keys", []) or []:
                        floats.append(
                            {"key": k, "x": m.get("x", 0), "y": m.get("y", 0)}
                        )
            except Exception:
                pass
            self._settings["floating_extensions"] = floats
            try:
                states_out = [
                    int(max(0, min(2, s))) for s in (self._config_states or [])
                ]
            except Exception:
                states_out = [2, 0, 0, 0]
            if len(states_out) < 4:
                states_out.extend([0] * (4 - len(states_out)))
            else:
                states_out = states_out[:4]
            self._settings["config_states"] = states_out
            self._settings["config_active"] = (
                self._config_active if self._config_active is not None else None
            )
            with open(self._settings_path, "w", encoding="utf-8") as f:
                json.dump(self._settings, f, ensure_ascii=False, indent=2)

        # ----- end save_settings mods block ----
        except Exception:
            log.exception("settings save failed")

    def _remove_one_from_toolbar(self, key: str):
        """Remove a single occurrence of an extension from the main toolbar."""
        try:
            idx = self.active_extensions.index(key)
        except Exception:
            return
        try:
            self.active_extensions.pop(idx)
        except Exception:
            return
        self._save_settings()
        self._render_toolbar()
        self._refresh_shelf_after_change()

    def _render_toolbar(self):
        for w in getattr(self, "_toolbar_widgets", []) or []:
            try:
                w.destroy()
            except Exception:
                pass
        self._toolbar_widgets = []

        # Active extension buttons
        self._ensure_unique_active_extensions()
        for key in self.active_extensions:
            # Hide keys that are already placed in a floating module
            if key in getattr(self, "_mod_of_key", {}):
                continue
            ext = self._extensions.get(key)
            if not ext:
                continue
            # Special scroll buttons run while hovered
            if key in ("SCROLU", "D"):
                direction = "up" if key == "SCROLU" else "down"
                b = self._make_scroll_button(
                    self.toolbar_row, ext["label"], direction, ext.get("hint")
                )
            else:
                b = self._make_dwell_button(
                    self.toolbar_row,
                    ext["label"],
                    ext["handler"],
                    ext.get("hint"),
                    ext_key=key,
                )
            # Enable drag-out to create floating window
            try:
                # Tag le bouton avec sa clé pour DRG depuis la toolbar
                b._ext_key = key
            except Exception:
                pass
            self._bind_drag_out(b, key)
            self._toolbar_widgets.append(b)

        # Spacer
        spacer = ctk.CTkLabel(self.toolbar_row, text="", width=4)
        spacer.pack(side="left", padx=2)
        self._toolbar_widgets.append(spacer)

        # Plus button (circular)
        try:
            from config import PLUS_SIZE, PLUS_CORNER
        except Exception:
            PLUS_SIZE, PLUS_CORNER = 26, 13
        plus_btn = ctk.CTkButton(
            self.toolbar_row,
            text="+",
            width=PLUS_SIZE,
            height=PLUS_SIZE,
            corner_radius=PLUS_CORNER,
            command=self._toggle_shelf,
            font=PLUS_FONT,
        )
        plus_btn.pack(side="right", padx=(8, 4))
        self._toolbar_widgets.append(plus_btn)

        # Resize window width to fit all toolbar items (keep height and position)
        try:
            self.root.update_idletasks()
            total_w = 16  # left/right padding
            for w in self._toolbar_widgets:
                try:
                    total_w += int(w.winfo_reqwidth()) + 8
                except Exception:
                    total_w += BTN_W + 8
            sw = self.root.winfo_screenwidth()
            max_w = max(300, sw - HUD_MARGIN * 2)
            desired = min(max(total_w, HUD_W), max_w)
            cur_h = self.root.winfo_height()
            self.root.geometry(
                f"{int(desired)}x{cur_h}+{self.root.winfo_x()}+{self.root.winfo_y()}"
            )
            self._last_width = int(desired)
        except Exception:
            pass
        try:
            if hasattr(self.root, "after"):
                if getattr(self, "_toolbar_width_job", None):
                    try:
                        self.root.after_cancel(self._toolbar_width_job)
                    except Exception:
                        pass
            self._toolbar_width_job = self.root.after(
                50, self._ensure_toolbar_width)
        except Exception:
            pass
        try:
            self._ensure_hint_layout()
        except Exception:
            pass

    def _ensure_toolbar_width(self):
        try:
            self._toolbar_width_job = None
        except Exception:
            pass
        row = getattr(self, "toolbar_row", None)
        if row is None:
            return
        try:
            if not row.winfo_exists():
                return
            self.root.update_idletasks()
            needed = int(row.winfo_reqwidth()) + 16
            sw = self.root.winfo_screenwidth()
            max_w = max(300, sw - HUD_MARGIN * 2)
            desired = min(
                max(needed, HUD_W, int(getattr(self, "_last_width", HUD_W))), max_w
            )
            cur_h = self.root.winfo_height()
            x = self.root.winfo_x()
            y = self.root.winfo_y()
            self.root.geometry(f"{int(desired)}x{cur_h}+{x}+{y}")
            self._last_width = int(desired)
        except Exception:
            pass

    def _bind_drag_out(self, button, key: str, from_shelf: bool = False):
        button._drag_origin = None
        button._dragging = False
        button._ghost = None
        button._suspended_for_drag = False

        def _on_press(e):
            try:
                button._drag_origin = (e.x_root, e.y_root)
                button._dragging = False
                # cancel any pending dwell action on press
                try:
                    if getattr(button, "_after", None):
                        self.root.after_cancel(button._after)
                        button._after = None
                except Exception:
                    pass
            except Exception:
                button._drag_origin = None

        def _on_motion(e):
            try:
                if button._drag_origin is None or key in getattr(
                    self, "_mod_of_key", {}
                ):
                    return
                dx = abs(e.x_root - button._drag_origin[0])
                dy = abs(e.y_root - button._drag_origin[1])
                # start dragging: show ghost following cursor
                if not button._dragging and (dx > 12 or dy > 12):
                    button._dragging = True
                    button._suspended_for_drag = True
                    try:
                        self._suspend_dwell_actions = (
                            max(0, int(self._suspend_dwell_actions)) + 1
                        )
                    except Exception:
                        self._suspend_dwell_actions = 1
                    # create a small ghost overlay inside the main window (not a new window)
                    try:
                        ghost = ctk.CTkFrame(self.root, corner_radius=8)
                        label = ctk.CTkLabel(
                            ghost, text=self._extensions[key]["label"])
                        label.pack(padx=6, pady=4)
                        # place relative to root
                        rx, ry = self.root.winfo_rootx(), self.root.winfo_rooty()
                        gx = max(0, e.x_root - rx + 8)
                        gy = max(0, e.y_root - ry + 8)
                        ghost.place(x=gx, y=gy)
                        try:
                            ghost.lift()
                        except Exception:
                            pass
                        button._ghost = ghost
                    except Exception:
                        button._ghost = None

                # move ghost with cursor
                if button._dragging and button._ghost is not None:
                    try:
                        rx, ry = self.root.winfo_rootx(), self.root.winfo_rooty()
                        gx = max(0, e.x_root - rx + 8)
                        gy = max(0, e.y_root - ry + 8)
                        button._ghost.place_configure(x=gx, y=gy)
                        try:
                            button._ghost.lift()
                        except Exception:
                            pass
                    except Exception:
                        pass
                # Show preview inside a module under cursor
                try:
                    mod_id = self._find_module_at(e.x_root, e.y_root)
                    if mod_id is not None:
                        orient = self._decide_drop_orientation(
                            mod_id, e.x_root, e.y_root
                        )
                        self._show_module_preview(
                            mod_id, orient, e.x_root, e.y_root)
                    else:
                        self._clear_module_preview()
                except Exception:
                    pass

                # do not finalize on motion; creation happens on release outside HUD
            except Exception:
                pass

        def _on_release(e):
            try:
                # create floating only if release occurs outside the main HUD area
                if button._dragging:
                    bx = self.wrap.winfo_rootx()
                    by = self.wrap.winfo_rooty()
                    bw = self.wrap.winfo_width()
                    bh = self.wrap.winfo_height()
                    outside = (
                        (e.x_root < bx)
                        or (e.x_root > bx + bw)
                        or (e.y_root < by)
                        or (e.y_root > by + bh)
                    )
                    # If dropped inside the extensions shelf, remove one occurrence from toolbar
                    inside_shelf = False
                    try:
                        if getattr(self, "_shelf_visible", False):
                            sx = self._shelf_row.winfo_rootx()
                            sy = self._shelf_row.winfo_rooty()
                            sw = self._shelf_row.winfo_width()
                            sh = self._shelf_row.winfo_height()
                            inside_shelf = (sx <= e.x_root <= sx + sw) and (
                                sy <= e.y_root <= sy + sh
                            )
                    except Exception:
                        inside_shelf = False

                    if inside_shelf:
                        if not from_shelf:
                            self._remove_one_from_toolbar(key)
                    elif outside:
                        self._move_extension_to_floating(
                            key, e.x_root, e.y_root)
            except Exception:
                pass
            finally:
                self._clear_module_preview()
                button._drag_origin = None
                button._dragging = False
                try:
                    if button._ghost is not None:
                        button._ghost.place_forget()
                        button._ghost.destroy()
                except Exception:
                    pass
                if getattr(button, "_suspended_for_drag", False):
                    try:
                        self._suspend_dwell_actions = max(
                            0, int(self._suspend_dwell_actions) - 1
                        )
                    except Exception:
                        self._suspend_dwell_actions = 0
                    button._suspended_for_drag = False
                button._ghost = None

        try:
            button.bind("<Button-1>", _on_press)
            button.bind("<B1-Motion>", _on_motion)
            button.bind("<ButtonRelease-1>", _on_release)
        except Exception:
            pass

    def _toolbar_key_at(self, x: int, y: int):
        """Retourne la clé d’extension sous le curseur dans la barre principale, sinon None."""
        try:
            row = getattr(self, "toolbar_row", None)
            if row is None:
                return None
            for w in list(row.winfo_children()):
                try:
                    k = getattr(w, "_ext_key", None)
                    if not k:
                        continue
                    wx, wy = w.winfo_rootx(), w.winfo_rooty()
                    ww, wh = w.winfo_width(), w.winfo_height()
                    if wx <= x <= wx + ww and wy <= y <= wy + wh:
                        return k
                except Exception:
                    pass
        except Exception:
            pass
        return None

    def _move_extension_to_floating(self, key: str, x: int = None, y: int = None):
        # Add into existing module under cursor, else create new module
        # Also remove one occurrence from the main toolbar so it doesn't return automatically
        try:
            if key in getattr(self, "active_extensions", []):
                try:
                    idx = self.active_extensions.index(key)
                    self.active_extensions.pop(idx)
                except Exception:
                    pass
        except Exception:
            pass
        try:
            mod_id = self._find_module_at(x, y)
        except Exception:
            mod_id = None
        if mod_id is None:
            mod_id = self._create_module_window(x, y)
        orient = self._decide_drop_orientation(mod_id, x, y)
        self._ensure_module_orientation(mod_id, orient)
        idx = self._compute_insert_index(mod_id, orient, x, y)
        self._add_key_to_module(mod_id, key, index=idx)
        self._repack_module_buttons(mod_id)
        self._resize_module(mod_id)
        self._clear_module_preview()
        self._render_toolbar()
        self._save_settings()
        self._refresh_shelf_after_change()

    def _refresh_shelf_after_change(self, delay: bool = True):
        if not getattr(self, "_shelf_visible", False):
            return
        mode = getattr(self, "_shelf_mode", None)
        target = "inactive" if mode == "inactive" else "all"

        def _rebuild():
            try:
                self._shelf_visible = False
                if target == "inactive":
                    self._show_shelf()
                else:
                    self._show_shelf_all()
            except Exception:
                try:
                    self._shelf_visible = True
                except Exception:
                    pass

        try:
            if delay and hasattr(self.root, "after"):
                self.root.after(10, _rebuild)
            else:
                _rebuild()
        except Exception:
            pass

    def _remove_key_from_module(self, key: str) -> bool:
        try:
            mapping = getattr(self, "_mod_of_key", {})
        except Exception:
            return False
        mod_id = mapping.get(key)
        if not mod_id:
            return False
        modules = getattr(self, "_modules", {}) or {}
        module = modules.get(mod_id)
        if not module:
            try:
                mapping.pop(key, None)
            except Exception:
                pass
            return False

        keys = module.get("keys") or []
        try:
            keys.remove(key)
        except ValueError:
            try:
                mapping.pop(key, None)
            except Exception:
                pass
            return False

        try:
            mapping.pop(key, None)
        except Exception:
            pass

        win = module.get("win")
        if not keys:
            hwnd = module.get("hwnd") or getattr(win, "_hud_hwnd", None)
            try:
                if win is not None:
                    win.destroy()
            except Exception:
                pass
            if hwnd is not None:
                try:
                    self._unregister_hud_window(hwnd)
                except Exception:
                    pass
            try:
                modules.pop(mod_id, None)
            except Exception:
                pass
        else:
            try:
                self._repack_module_buttons(mod_id)
                self._resize_module(mod_id)
            except Exception:
                pass

        return True

    def _spawn_floating_window(self, key: str, x: int = None, y: int = None):
        ext = self._extensions.get(key)
        if not ext:
            return
        win = ctk.CTkToplevel(self.root)
        try:
            win.overrideredirect(True)
        except Exception:
            pass
        try:
            win.attributes("-topmost", True)
        except Exception:
            pass

        # Minimal floating toolbar container (tight, with small border)
        frame = ctk.CTkFrame(
            win,
            corner_radius=6,
            border_width=1,
            border_color="#3a3a3a",
        )
        frame.pack(padx=1, pady=1)
        try:
            frame.pack_propagate(True)  # size to children
        except Exception:
            pass

        # Inner content row (tight padding)
        content = ctk.CTkFrame(frame, fg_color="transparent")
        content.pack(padx=14, pady=(16, 12))

        # drag window support
        drag = {"x": 0, "y": 0, "active": False}

        def start_drag(e):
            drag["x"], drag["y"], drag["active"] = e.x, e.y, True

        def on_drag(e):
            if not drag["active"]:
                return
            try:
                win.geometry(
                    f"+{win.winfo_x()+e.x-drag['x']}+{win.winfo_y()+e.y-drag['y']}"
                )
            except Exception:
                pass

        def end_drag(_e):
            drag["active"] = False
            # persist new pos
            self._save_settings()

        frame.bind("<Button-1>", start_drag)
        frame.bind("<B1-Motion>", on_drag)
        frame.bind("<ButtonRelease-1>", end_drag)
        # allow dragging even when grabbing the inner row
        try:
            content.bind("<Button-1>", start_drag)
            content.bind("<B1-Motion>", on_drag)
            content.bind("<ButtonRelease-1>", end_drag)
        except Exception:
            pass

        # button + small close
        if key in ("SCROLU", "D"):
            direction = "up" if key == "SCROLU" else "down"
            btn = self._make_scroll_button(
                content, ext["label"], direction, ext.get("hint")
            )
        else:
            btn = self._make_dwell_button(
                content, ext["label"], ext["handler"], ext.get("hint"), ext_key=key
            )
        # generous padding inside modules
        try:
            btn.pack_configure(side="left", padx=10, pady=6)
        except Exception:
            pass

        # Small overlay close at top-right of frame
        close = ctk.CTkButton(
            frame,
            text="X",
            width=14,
            height=14,
            corner_radius=7,
            fg_color="#aa3333",
            hover_color="#992222",
            command=lambda k=key, w=win: self._close_floating(k, w),
        )
        try:
            close.place(relx=1.0, rely=0.0, x=-2, y=2, anchor="ne")
            try:
                close.lift()
            except Exception:
                pass
        except Exception:
            close.pack(side="right", padx=(2, 4), pady=2)

        # initial geometry
        window_hwnd = None
        try:
            win.update_idletasks()
            window_hwnd = int(win.winfo_id())
        except Exception:
            window_hwnd = None
        if window_hwnd is not None:
            self._register_hud_window(window_hwnd)
            try:
                win._hud_hwnd = window_hwnd
            except Exception:
                pass
        try:
            # ensure enough top padding so close does not overlap the tool
            try:
                close_h = int(close.winfo_reqheight())
                top_pad = max(12, close_h + 6)
                content.pack_configure(padx=6, pady=(top_pad, 6))
                win.update_idletasks()
            except Exception:
                pass

            req_w = max(int(frame.winfo_reqwidth()),
                        int(content.winfo_reqwidth()) + 2)
            req_h = max(
                int(frame.winfo_reqheight()), int(
                    content.winfo_reqheight()) + 2
            )
            # add a few pixels more for breathing room
            req_w += 6
            req_h += 6
            if x is None or y is None:
                px, py = pyautogui.position()
                x, y = max(0, px - req_w // 2), max(0, py - req_h // 2)
            win.geometry(f"{req_w}x{req_h}+{int(x)}+{int(y)}")
            try:
                win.minsize(req_w, req_h)
            except Exception:
                pass
        except Exception:
            pass

        self._render_toolbar()
        self._save_settings()

    def _close_floating(self, key: str, win):
        # Legacy closer for old single-key floaters: route to module closer
        try:
            self._close_module_by_win(win)
        except Exception:
            try:
                win.destroy()
            except Exception:
                pass
        try:
            self._unregister_hud_window(getattr(win, "_hud_hwnd", None))
        except Exception:
            pass
        self._render_toolbar()
        self._save_settings()

    # ---------------------- Modules (multi-extension toolbars) ----------------------
    def _create_module_window(
        self, x: int = None, y: int = None, config_index: int | None = None
    ):
        try:
            cfg_idx = self._resolve_target_config(config_index)
            win = ctk.CTkToplevel(self.root)
            try:
                win.overrideredirect(True)
            except Exception:
                pass
            try:
                win.attributes("-topmost", True)
            except Exception:
                pass

            frame = ctk.CTkFrame(
                win, corner_radius=6, border_width=1, border_color="#3a3a3a"
            )
            frame.pack(padx=1, pady=1)
            try:
                frame.pack_propagate(True)
            except Exception:
                pass

            content = ctk.CTkFrame(frame, fg_color="transparent")
            content.pack(padx=4, pady=(8, 4))

            # drag support (frame + content)
            drag = {"x": 0, "y": 0, "active": False}

            def start_drag(e):
                drag.update({"x": e.x, "y": e.y, "active": True})

            def on_drag(e):
                if not drag["active"]:
                    return
                try:
                    win.geometry(
                        f"+{win.winfo_x()+e.x-drag['x']}+{win.winfo_y()+e.y-drag['y']}"
                    )
                except Exception:
                    pass

            def end_drag(_e):
                drag["active"] = False
                self._save_settings()

            for w in (frame, content):
                try:
                    w.bind("<Button-1>", start_drag)
                    w.bind("<B1-Motion>", on_drag)
                    w.bind("<ButtonRelease-1>", end_drag)
                except Exception:
                    pass

            # close button
            close = ctk.CTkButton(
                frame,
                text="X",
                width=14,
                height=14,
                corner_radius=7,
                fg_color="#aa3333",
                hover_color="#992222",
                command=lambda w=win: self._close_module_by_win(w),
            )
            try:
                close.place(relx=1.0, rely=0.0, x=-2, y=2, anchor="ne")
                try:
                    close.lift()
                except Exception:
                    pass
            except Exception:
                close.pack(side="right", padx=(2, 4), pady=2)

            module_hwnd = None
            try:
                win.update_idletasks()
                module_hwnd = int(win.winfo_id())
            except Exception:
                module_hwnd = None
            if module_hwnd is not None:
                self._register_hud_window(module_hwnd)
                try:
                    win._hud_hwnd = module_hwnd
                except Exception:
                    pass
            # minimal geometry near pointer
            try:
                win.update_idletasks()
                req_w = max(
                    int(frame.winfo_reqwidth()), int(
                        content.winfo_reqwidth()) + 2
                )
                req_h = max(
                    int(frame.winfo_reqheight()), int(
                        content.winfo_reqheight()) + 2
                )
                if x is None or y is None:
                    px, py = pyautogui.position()
                    x, y = max(0, px - req_w // 2), max(0, py - req_h // 2)
                win.geometry(f"{req_w}x{req_h}+{int(x)}+{int(y)}")
            except Exception:
                pass

            # register module
            if not hasattr(self, "_modules"):
                self._modules = {}
            if not hasattr(self, "_next_mod_id"):
                self._next_mod_id = 1
            mod_id = self._next_mod_id
            self._next_mod_id += 1
            self._modules[mod_id] = {
                "win": win,
                "frame": frame,
                "content": content,
                "keys": [],
                "orient": "h",
                "hwnd": module_hwnd,
                "config": cfg_idx,
            }
            self._apply_config_visibility()
            return mod_id
        except Exception:
            log.exception("create module failed")
            return None

    def _add_key_to_module(self, mod_id: int, key: str, index: int = None):
        module = (getattr(self, "_modules", {}) or {}).get(mod_id)
        if not module:
            return
        if not hasattr(self, "_mod_of_key"):
            self._mod_of_key = {}
        if key in self._mod_of_key:
            return
        ext = self._extensions.get(key)
        if not ext:
            return
        keys = module["keys"]
        if index is None or index < 0 or index > len(keys):
            keys.append(key)
        else:
            keys.insert(index, key)
        self._mod_of_key[key] = mod_id

    def _resize_module(self, mod_id: int):
        module = (getattr(self, "_modules", {}) or {}).get(mod_id)
        if not module:
            return
        win = module["win"]
        frame = module["frame"]
        content = module["content"]
        try:
            win.update_idletasks()
            req_w = (
                max(int(frame.winfo_reqwidth()), int(
                    content.winfo_reqwidth()) + 2) + 6
            )
            req_h = (
                max(int(frame.winfo_reqheight()), int(
                    content.winfo_reqheight()) + 2)
                + 6
            )
            win.geometry(f"{req_w}x{req_h}+{win.winfo_x()}+{win.winfo_y()}")
            try:
                win.minsize(req_w, req_h)
            except Exception:
                pass
        except Exception:
            pass

    def _repack_module_buttons(self, mod_id: int):
        module = (getattr(self, "_modules", {}) or {}).get(mod_id)
        if not module:
            return
        parent = module["content"]
        for w in list(parent.winfo_children()):
            try:
                w.destroy()
            except Exception:
                pass
        side = "left" if module.get("orient", "h") == "h" else "top"
        for k in module.get("keys", []):
            ext = self._extensions.get(k)
            if not ext:
                continue
            if k in ("SCROLU", "D"):
                direction = "up" if k == "SCROLU" else "down"
                btn = self._make_scroll_button(
                    parent, ext["label"], direction, ext.get("hint")
                )
            else:
                btn = self._make_dwell_button(
                    parent, ext["label"], ext["handler"], ext.get("hint"), ext_key=k
                )
            try:
                btn.pack_configure(side=side, padx=10, pady=6)
            except Exception:
                pass

    def _decide_drop_orientation(self, mod_id: int, x: int, y: int) -> str:
        module = (getattr(self, "_modules", {}) or {}).get(mod_id)
        if not module:
            return "h"
        c = module["content"]
        try:
            cx, cy = c.winfo_rootx(), c.winfo_rooty()
            cw, ch = c.winfo_width(), c.winfo_height()
            dx = min(abs(x - cx), abs(x - (cx + cw)))
            dy = min(abs(y - cy), abs(y - (cy + ch)))
            return "v" if dy < dx else "h"
        except Exception:
            return "h"

    def _ensure_module_orientation(self, mod_id: int, orient: str):
        module = (getattr(self, "_modules", {}) or {}).get(mod_id)
        if not module:
            return
        o = "v" if orient == "v" else "h"
        if module.get("orient", "h") != o:
            module["orient"] = o
            self._repack_module_buttons(mod_id)

    def _compute_insert_index(self, mod_id: int, orient: str, x: int, y: int) -> int:
        module = (getattr(self, "_modules", {}) or {}).get(mod_id)
        if not module:
            return 1_000_000
        c = module["content"]
        children = [
            w for w in list(c.winfo_children()) if not getattr(w, "_is_preview", False)
        ]
        if not children:
            return 0
        try:
            if orient == "v":
                items = sorted(
                    [(w, w.winfo_rooty() + w.winfo_height() // 2)
                     for w in children],
                    key=lambda t: t[1],
                )
                for i, (_w, mid) in enumerate(items):
                    if y < mid:
                        return i
                return len(items)
            else:
                items = sorted(
                    [(w, w.winfo_rootx() + w.winfo_width() // 2)
                     for w in children],
                    key=lambda t: t[1],
                )
                for i, (_w, mid) in enumerate(items):
                    if x < mid:
                        return i
                return len(items)
        except Exception:
            return 1_000_000

    def _show_module_preview(self, mod_id: int, orient: str, x: int, y: int):
        """Show a stable live preview by inserting/moving a placeholder only
        when the target index/orientation actually changes, with light throttling."""
        try:
            module = (getattr(self, "_modules", {}) or {}).get(mod_id)
            if not module:
                return
            content = module["content"]

            # Light throttle (avoid jitter on tiny mouse moves)
            now = time.time()
            last = getattr(self, "_mod_preview_ts", 0.0)
            if now - last < 0.03:  # ~33 FPS max updates
                return

            # Compute target placement ignoring current preview
            idx = self._compute_insert_index(mod_id, orient, x, y)
            self._ensure_module_orientation(mod_id, orient)
            side = "left" if module.get("orient", "h") == "h" else "top"

            prev = getattr(self, "_mod_preview", None)
            ph = None
            if (
                isinstance(prev, dict)
                and prev.get("mod_id") == mod_id
                and prev.get("orient") == orient
            ):
                ph = prev.get("widget") if prev else None

            # Create placeholder if missing
            if ph is None or not getattr(ph, "winfo_exists", lambda: 0)():
                # Determine typical size from first child
                btn_w, btn_h = BTN_W, BTN_H
                try:
                    for cw in [
                        w
                        for w in content.winfo_children()
                        if not getattr(w, "_is_preview", False)
                    ]:
                        btn_w = max(btn_w, int(cw.winfo_reqwidth()))
                        btn_h = max(btn_h, int(cw.winfo_reqheight()))
                        break
                except Exception:
                    pass
                ph = ctk.CTkFrame(
                    content, width=btn_w, height=btn_h, fg_color="#58616b"
                )
                ph._is_preview = True

            # Move placeholder only if target changed
            changed = True
            if (
                isinstance(prev, dict)
                and prev.get("index") == idx
                and prev.get("orient") == orient
                and prev.get("mod_id") == mod_id
            ):
                changed = False

            if changed:
                try:
                    ph.pack_forget()
                except Exception:
                    pass
                # Determine widget to pack before, excluding preview itself
                children = [
                    w
                    for w in content.winfo_children()
                    if not getattr(w, "_is_preview", False)
                ]
                target_before = children[idx] if idx < len(children) else None
                try:
                    if target_before is not None:
                        ph.pack(side=side, padx=10, pady=6,
                                before=target_before)
                    else:
                        ph.pack(side=side, padx=10, pady=6)
                except Exception:
                    try:
                        ph.pack(side=side, padx=10, pady=6)
                    except Exception:
                        pass
                # Resize module only when layout changed
                self._resize_module(mod_id)

            self._mod_preview = {
                "mod_id": mod_id,
                "orient": orient,
                "index": idx,
                "widget": ph,
            }
            self._mod_preview_ts = now
        except Exception:
            pass

    def _clear_module_preview(self):
        try:
            if hasattr(self, "_mod_preview") and self._mod_preview is not None:
                ph = self._mod_preview
                if isinstance(ph, dict):
                    w = ph.get("widget")
                    try:
                        if w is not None and w.winfo_exists() == 1:
                            w.pack_forget()
                            w.destroy()
                    except Exception:
                        pass
                self._mod_preview = None
                self._mod_preview_ts = 0.0
        except Exception:
            pass

    def _find_module_at(self, x: int, y: int):
        try:
            for mod_id, m in (getattr(self, "_modules", {}) or {}).items():
                if not m.get("visible", True):
                    continue
                w = m.get("win")
                wx, wy = w.winfo_x(), w.winfo_y()
                ww, wh = w.winfo_width(), w.winfo_height()
                if (
                    x is not None
                    and y is not None
                    and wx <= x <= wx + ww
                    and wy <= y <= wy + wh
                ):
                    return mod_id
        except Exception:
            pass
        return None

    def _close_module_by_win(self, win):
        target = None
        hwnd_to_remove = None
        modules = getattr(self, "_modules", {}) or {}
        for mod_id, m in list(modules.items()):
            if m.get("win") == win:
                target = mod_id
                hwnd_to_remove = m.get("hwnd") or getattr(
                    win, "_hud_hwnd", None)
                break
        if hwnd_to_remove is None:
            hwnd_to_remove = getattr(win, "_hud_hwnd", None)
        try:
            win.destroy()
        except Exception:
            pass
        if hwnd_to_remove is not None:
            try:
                self._unregister_hud_window(hwnd_to_remove)
            except Exception:
                pass
        if target is None:
            return
        keys = list(modules.get(target, {}).get("keys") or [])
        modules.pop(target, None)
        for k in keys:
            if hasattr(self, "_mod_of_key"):
                self._mod_of_key.pop(k, None)
        self._render_toolbar()
        self._save_settings()
        self._refresh_shelf_after_change()

    def _toggle_shelf(self):
        if self._shelf_visible:
            self._hide_shelf()
        else:
            # Use the palette that always shows all extensions
            try:
                self._show_shelf_all()
            except Exception:
                # fallback to legacy
                self._show_shelf()

    def _show_shelf(self):
        if self._shelf_visible:
            return
        self._shelf_mode = "inactive"
        # Rebuild shelf content with non-active extensions
        for w in getattr(self, "_shelf_widgets", []) or []:
            try:
                w.destroy()
            except Exception:
                pass
        self._shelf_widgets = []

        inner = ctk.CTkFrame(self._shelf_row, fg_color="transparent")
        inner.pack(fill="x", padx=8, pady=SHELF_PADY)
        self._shelf_widgets.append(inner)

        def add_to_toolbar(key):
            try:
                self._remove_key_from_module(key)
            except Exception:
                pass
            if key not in self.active_extensions:
                self.active_extensions.append(key)
            self._ensure_unique_active_extensions()
            self._save_settings()
            self._render_toolbar()
            self._refresh_shelf_after_change(delay=False)

        buttons = []
        for key, ext in self._extensions.items():
            if key in self.active_extensions:
                continue
            b = ctk.CTkButton(
                inner,
                text=ext["label"],
                width=SHELF_BTN_W,
                height=SHELF_BTN_H,
                corner_radius=SHELF_CORNER,
                font=SHELF_BTN_FONT,
                fg_color=SHELF_BTN_FG,
                hover_color=SHELF_BTN_HOVER,
                text_color=SHELF_BTN_TEXT,
                command=lambda k=key: add_to_toolbar(k),
            )
            try:
                b._ext_key = key
            except Exception:
                pass
            self._bind_drag_out(b, key, from_shelf=True)
            show_hint, clear_hint = self._prepare_hover_hint(
                b, ext.get("hint"))
            self._attach_extension_hover(b, show_hint, clear_hint)
            self._shelf_widgets.append(b)
            buttons.append(b)

        if not buttons:
            lbl = ctk.CTkLabel(
                inner, text="Aucune extension disponible", text_color="#cccccc"
            )
            lbl.grid(row=0, column=0, padx=6, pady=4, sticky="w")
            self._shelf_widgets.append(lbl)
            try:
                inner.update_idletasks()
                pad_top = (
                    SHELF_PADY[0]
                    if isinstance(SHELF_PADY, (tuple, list))
                    else (SHELF_PADY or 0)
                )
                pad_bottom = (
                    SHELF_PADY[1]
                    if isinstance(SHELF_PADY, (tuple, list))
                    else (SHELF_PADY or 0)
                )
                row_height = max(
                    0, int(inner.winfo_reqheight()) +
                    int(pad_top) + int(pad_bottom)
                )
                self._shelf_row.configure(height=row_height)
                self._current_shelf_height = row_height
                self._resize_root_height()
            except Exception:
                pass
        else:

            def _redraw(_=None, frame=inner, btns=buttons):
                self._layout_shelf_buttons(frame, btns)

            inner.bind("<Configure>", _redraw)
            _redraw()

        try:
            # Insert shelf under the blue bar or VOICE picker if visible
            anchor = None
            try:
                if getattr(self.gpt, "_picker_visible", False):
                    anchor = getattr(self.gpt, "_picker_row", None)
            except Exception:
                anchor = None
            if anchor is None:
                anchor = self.bar
            self._shelf_row.pack(after=anchor, fill="x", padx=8)
        except Exception:
            self._shelf_row.pack(fill="x", padx=8)
        try:
            self._shelf_row.pack_propagate(False)
        except Exception:
            pass

        self._shelf_visible = True
        try:
            self._resize_root_height()
        except Exception:
            pass

    def _hide_shelf(self):
        if not self._shelf_visible:
            return
        try:
            self._shelf_row.pack_forget()
        except Exception:
            pass
        self._shelf_visible = False
        self._shelf_mode = "all"
        self._current_shelf_height = 0
        try:
            self.root.update_idletasks()
            self._base_height = int(self.root.winfo_reqheight())
        except Exception:
            pass
        try:
            self._resize_root_height()
        except Exception:
            pass
        self._last_shelf_h = 0

    def _show_shelf_all(self):
        if self._shelf_visible:
            return
        self._shelf_mode = "all"
        # Rebuild shelf content with the full extensions palette (always visible)
        for w in getattr(self, "_shelf_widgets", []) or []:
            try:
                w.destroy()
            except Exception:
                pass
        self._shelf_widgets = []

        inner = ctk.CTkFrame(self._shelf_row, fg_color="transparent")
        inner.pack(fill="x", padx=8, pady=SHELF_PADY)
        self._shelf_widgets.append(inner)

        def add_to_toolbar(key):
            try:
                self._remove_key_from_module(key)
            except Exception:
                pass
            # Keep a single occurrence per extension in the main toolbar
            if key not in self.active_extensions:
                try:
                    self.active_extensions.append(key)
                except Exception:
                    pass
            self._ensure_unique_active_extensions()
            self._save_settings()
            self._render_toolbar()
            self._refresh_shelf_after_change(delay=False)

        buttons = []
        for key, ext in self._extensions.items():
            b = ctk.CTkButton(
                inner,
                text=ext["label"],
                width=SHELF_BTN_W,
                height=SHELF_BTN_H,
                corner_radius=SHELF_CORNER,
                font=SHELF_BTN_FONT,
                fg_color=SHELF_BTN_FG,
                hover_color=SHELF_BTN_HOVER,
                text_color=SHELF_BTN_TEXT,
                command=lambda k=key: add_to_toolbar(k),
            )
            try:
                b._ext_key = key
            except Exception:
                pass
            self._bind_drag_out(b, key, from_shelf=True)
            show_hint, clear_hint = self._prepare_hover_hint(
                b, ext.get("hint"))
            self._attach_extension_hover(b, show_hint, clear_hint)
            self._shelf_widgets.append(b)
            buttons.append(b)

        if not buttons:
            lbl = ctk.CTkLabel(
                inner, text="Aucune extension", text_color="#cccccc")
            lbl.grid(row=0, column=0, padx=6, pady=4, sticky="w")
            self._shelf_widgets.append(lbl)
            try:
                inner.update_idletasks()
                pad_top = (
                    SHELF_PADY[0]
                    if isinstance(SHELF_PADY, (tuple, list))
                    else (SHELF_PADY or 0)
                )
                pad_bottom = (
                    SHELF_PADY[1]
                    if isinstance(SHELF_PADY, (tuple, list))
                    else (SHELF_PADY or 0)
                )
                row_height = max(
                    0, int(inner.winfo_reqheight()) +
                    int(pad_top) + int(pad_bottom)
                )
                self._shelf_row.configure(height=row_height)
                self._current_shelf_height = row_height
                self._resize_root_height()
            except Exception:
                pass
        else:

            def _redraw(_=None, frame=inner, btns=buttons):
                self._layout_shelf_buttons(frame, btns)

            inner.bind("<Configure>", _redraw)
            _redraw()

        try:
            # Insert shelf under the blue bar or VOICE picker if visible
            anchor = None
            try:
                if getattr(self.gpt, "_picker_visible", False):
                    anchor = getattr(self.gpt, "_picker_row", None)
            except Exception:
                anchor = None
            if anchor is None:
                anchor = self.bar
            self._shelf_row.pack(after=anchor, fill="x", padx=8)
        except Exception:
            self._shelf_row.pack(fill="x", padx=8)
        try:
            self._shelf_row.pack_propagate(False)
        except Exception:
            pass

        self._shelf_visible = True
        try:
            self._resize_root_height()
        except Exception:
            pass

    def _set_mode_cb(self, mode_text: str):
        self._current_mode = mode_text
        self.info_lbl.configure(text=self._info_text(mode_text))

    def _refresh_status(self):
        self.status_lbl.configure(text="ON" if self.running else "OFF")
        self.dot_lbl.configure(
            text_color="#2ecc71" if self.running else "#e74c3c")
        if self.del_mode:
            mode = "DEL"
        elif self.ent_mode:
            mode = "ENT"
        elif self.pyth_mode:
            mode = "PYTH"
        elif self.cola_mode:
            mode = "COLA"
        elif self.col_mode:
            mode = "COL"
        elif self.cop_mode:
            mode = "COP"
        elif self.clicd_mode:
            mode = "CLICD"
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

    def _stop_voice(self):
        try:
            self._stop_voice()
        except Exception:
            pass
        self._set_extension_highlight("VOICE", False)

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
            # also block when interacting with the extensions shelf
            if hasattr(self, "_shelf_row") and self._is_descendant(
                self._shelf_row, widget
            ):
                return True
        except Exception:
            pass
        return False

    def _start_drag(self, e):
        # Deplacement seulement si clic dans l'entete (ou ses descendants)
        if hasattr(self, "_drag_header"):
            try:
                if not self._is_descendant(self._drag_header, e.widget):
                    self._drag_active = False
                    return
            except Exception:
                pass
        # Bloquer si on clique dans les zones interactives (VOICE picker, shelf, etc.)
        if self._should_block_drag(e.widget):
            log.info("[APP] suppress window drag on VOICE picker")
            self._drag_active = False
            return
        self._drag["x"], self._drag["y"] = e.x, e.y
        self._drag_active = True

    def _on_drag(self, e):
        if not self._drag_active:
            return
        self.root.geometry(
            f"+{self.root.winfo_x()+e.x-self._drag['x']}+{self.root.winfo_y()+e.y-self._drag['y']}"
        )

    def _end_drag(self, _e):
        self._drag_active = False

    # ---------------------- Mode toggles ----------------------
    def _toggle_running(self):
        self.running = not self.running
        self._set_extension_highlight("AUTO", self.running)

        self._refresh_status()

    def _toggle_selection(self):
        self._reset_shot()
        self.cola_mode = False
        self.col_mode = False
        self.cop_mode = False
        self.clicd_mode = False
        self.drg_mode = False
        self.drg_holding = False
        self._cancel_pyth()
        self._stop_voice()
        self.selection_mode = not self.selection_mode
        self._set_extension_highlight("COLA", False)
        self._set_extension_highlight("COL", False)
        self._set_extension_highlight("COP", False)
        self._set_extension_highlight("CLICD", False)
        self._set_extension_highlight("DRG", False)
        self._set_extension_highlight("VOICE", False)
        self.selection_phase_down = False
        self.selection_arm_until = (
            time.time() + SEL_ARM_SECONDS if self.selection_mode else 0.0
        )
        if self.selection_mode:
            self.hint.configure(
                text=f"SEL: prêt dans {SEL_ARM_SECONDS:.1f}s — placez-vous au début du texte"
            )
            self.bar.configure(progress_color=BAR_ARM)
            self._set_mode_cb("SEL")
        else:
            self.hint.configure(text="")
            self.bar.configure(progress_color=BAR_DEFAULT)
            self._set_mode_cb("CLICK")
        self._set_extension_highlight("SEL", self.selection_mode)
        self._refresh_status()

    def _reset_shot(self):
        self.screenshot_mode = False
        self.screenshot_phase_down = False
        self.shot_anchor = None
        self.hint.configure(text="")
        self.bar.configure(progress_color=BAR_DEFAULT)
        self._set_extension_highlight("SHOT", False)

    def _cancel_pyth(self):
        self.pyth_mode = False
        self.pyth_arm_until = 0.0
        self.pyth_started_at = 0.0
        self._set_extension_highlight("PYTH", False)

    def _cancel_csharp(self):
        """Désactive le mode CSHARP sans exécuter."""
        self.csharp_mode = False
        self.csharp_arm_until = 0.0
        self.csharp_started_at = 0.0
        self._set_extension_highlight("CSHARP", False)

    def _start_shot(self):
        if self.selection_mode:
            self._toggle_selection()
        self.cola_mode = False
        self.col_mode = False
        self.cop_mode = False
        self.clicd_mode = False
        self.drg_mode = False
        self.drg_holding = False
        self._cancel_pyth()
        self._stop_voice()
        self.screenshot_mode = True
        self.screenshot_phase_down = False
        self.shot_anchor = None
        self.screenshot_arm_until = time.time() + SHOT_ARM_SECONDS
        self.hint.configure(
            text=f"SHOT: prêt dans {SHOT_ARM_SECONDS:.1f}s — placez-vous"
        )
        self.bar.configure(progress_color=BAR_ARM)
        self._set_mode_cb("SHOT")
        self._set_extension_highlight("SHOT", True)
        self._refresh_status()

    def _start_cola(self):
        """Armement puis Ctrl+A / Delete / Ctrl+V (remplacement intégral)."""
        self.selection_mode = False
        self.screenshot_mode = False
        self.col_mode = False
        self.cop_mode = False
        self.clicd_mode = False
        self.drg_mode = False
        self.drg_holding = False
        self._cancel_pyth()
        self._stop_voice()
        self._set_extension_highlight("SEL", False)
        self._set_extension_highlight("SHOT", False)
        self._set_extension_highlight("COL", False)
        self._set_extension_highlight("COP", False)
        self._set_extension_highlight("CLICD", False)
        self._set_extension_highlight("DRG", False)
        self.cola_mode = True
        self.cola_started_at = time.time()
        self.cola_arm_until = self.cola_started_at + COLA_ARM_SECONDS
        self.hint.configure(
            text=f"COLA: prêt dans {COLA_ARM_SECONDS:.1f}s — placez-vous"
        )
        self.bar.configure(progress_color=BAR_ARM)
        self._set_mode_cb("COLA")
        self._set_extension_highlight("COLA", True)
        self._refresh_status()

    def _start_selcp(self):
        """Active/désactive le mode SELCP : sélection + copie automatique."""
        self.selcp_mode = not self.selcp_mode
        self.selcp_phase_down = False
        self.selcp_arm_until = time.time() + SEL_ARM_SECONDS if self.selcp_mode else 0.0
        if self.selcp_mode:
            self.hint.configure(
                text=f"SELCP: prêt dans {SEL_ARM_SECONDS:.1f}s — placez-vous au début du texte"
            )
            self.bar.configure(progress_color=BAR_ARM)
            self._set_mode_cb("SELCP")
        else:
            self.hint.configure(text="")
            self.bar.configure(progress_color=BAR_DEFAULT)
            self._set_mode_cb("CLICK")
        self._set_extension_highlight("SELCP", self.selcp_mode)
        self._refresh_status()

    def _start_seldl(self):
        """Active/désactive le mode SELDL : sélection + suppression."""
        self.seldl_mode = not self.seldl_mode
        self.seldl_phase_down = False
        self.seldl_arm_until = time.time() + SEL_ARM_SECONDS if self.seldl_mode else 0.0
        if self.seldl_mode:
            self.hint.configure(
                text=f"SELDL: prêt dans {SEL_ARM_SECONDS:.1f}s — placez-vous au début du texte"
            )
            self.bar.configure(progress_color=BAR_ARM)
            self._set_mode_cb("SELDL")
        else:
            self.hint.configure(text="")
            self.bar.configure(progress_color=BAR_DEFAULT)
            self._set_mode_cb("CLICK")
        self._set_extension_highlight("SELDL", self.seldl_mode)
        self._refresh_status()

    def _start_col(self):
        """Armement puis Ctrl+V (coller simple, sans suppression préalable)."""
        self.selection_mode = False
        self.screenshot_mode = False
        self.cola_mode = False
        self.cop_mode = False
        self.clicd_mode = False
        self.drg_mode = False
        self.drg_holding = False
        self._cancel_pyth()
        self._stop_voice()
        self._set_extension_highlight("SEL", False)
        self._set_extension_highlight("SHOT", False)
        self._set_extension_highlight("COLA", False)
        self._set_extension_highlight("COP", False)
        self._set_extension_highlight("CLICD", False)
        self._set_extension_highlight("DRG", False)
        self.col_mode = True
        self.col_started_at = time.time()
        self.col_arm_until = self.col_started_at + COL_ARM_SECONDS
        self.hint.configure(
            text=f"COL: prêt dans {COL_ARM_SECONDS:.1f}s — placez-vous")
        self.bar.configure(progress_color=BAR_ARM)
        self._set_mode_cb("COL")
        self._set_extension_highlight("COL", True)
        self._refresh_status()

    def _start_cop(self):
        """Armement puis Ctrl+A / Ctrl+C (sans supprimer, sans coller)."""
        self.selection_mode = False
        self.screenshot_mode = False
        self.cola_mode = False
        self.col_mode = False
        self.clicd_mode = False
        self.drg_mode = False
        self.drg_holding = False
        self._cancel_pyth()
        self._stop_voice()
        self._set_extension_highlight("SEL", False)
        self._set_extension_highlight("SHOT", False)
        self._set_extension_highlight("COLA", False)
        self._set_extension_highlight("COL", False)
        self._set_extension_highlight("CLICD", False)
        self._set_extension_highlight("DRG", False)
        self.cop_mode = True
        self.cop_started_at = time.time()
        self.cop_arm_until = self.cop_started_at + COP_ARM_SECONDS
        self.hint.configure(
            text=f"COP: prêt dans {COP_ARM_SECONDS:.1f}s — placez-vous")
        self.bar.configure(progress_color=BAR_ARM)
        self._set_mode_cb("COP")
        self._set_extension_highlight("COP", True)
        self._refresh_status()

    def _start_clicd(self):
        """Armement puis clic droit à la fin de l'immobilisation."""
        self.selection_mode = False
        self.screenshot_mode = False
        self.cola_mode = False
        self.col_mode = False
        self.cop_mode = False
        self.del_mode = False
        self.ent_mode = False
        self.drg_mode = False
        self.drg_holding = False
        self._cancel_pyth()
        self._stop_voice()
        self._set_extension_highlight("SEL", False)
        self._set_extension_highlight("SHOT", False)
        self._set_extension_highlight("COLA", False)
        self._set_extension_highlight("COL", False)
        self._set_extension_highlight("COP", False)
        self._set_extension_highlight("DEL", False)
        self._set_extension_highlight("ENT", False)
        self._set_extension_highlight("DRG", False)
        now = time.time()
        self.clicd_mode = True
        self.clicd_started_at = now
        self.clicd_arm_until = now + CLICD_ARM_SECONDS
        self.hint.configure(
            text=f"CLICD: prêt dans {CLICD_ARM_SECONDS:.1f}s — placez-vous"
        )
        self.bar.configure(progress_color=BAR_ARM)
        self._set_mode_cb("CLICD")
        self._set_extension_highlight("CLICD", True)
        self._refresh_status()

    def _start_ent(self):
        """Armement puis Enter sur immobilisation (avec focus préalable)."""
        self.selection_mode = False
        self.screenshot_mode = False
        self.cola_mode = False
        self.col_mode = False
        self.cop_mode = False
        self.clicd_mode = False
        self.drg_mode = False
        self.drg_holding = False
        self._cancel_pyth()
        self._stop_voice()
        self._set_extension_highlight("SEL", False)
        self._set_extension_highlight("SHOT", False)
        self._set_extension_highlight("COLA", False)
        self._set_extension_highlight("COL", False)
        self._set_extension_highlight("COP", False)
        self._set_extension_highlight("CLICD", False)
        self._set_extension_highlight("DRG", False)
        self.ent_mode = True
        self.ent_started_at = time.time()
        self.ent_arm_until = self.ent_started_at + ENT_ARM_SECONDS
        self.hint.configure(
            text=f"ENT: prêt dans {ENT_ARM_SECONDS:.1f}s – placez-vous")
        self.bar.configure(progress_color=BAR_ARM)
        self._set_mode_cb("ENT")
        self._set_extension_highlight("ENT", True)
        self._refresh_status()

    def _start_pyth(self):
        """Armement puis copie du script associé avant validation immédiate (Enter)."""
        self.selection_mode = False
        self.screenshot_mode = False
        self.cola_mode = False
        self.col_mode = False
        self.cop_mode = False
        self.clicd_mode = False
        self.drg_mode = False
        self.drg_holding = False
        self.ent_mode = False
        self.del_mode = False
        self._cancel_pyth()
        self._stop_voice()
        self._set_extension_highlight("SEL", False)
        self._set_extension_highlight("SHOT", False)
        self._set_extension_highlight("COLA", False)
        self._set_extension_highlight("COL", False)
        self._set_extension_highlight("COP", False)
        self._set_extension_highlight("CLICD", False)
        self._set_extension_highlight("DRG", False)
        self._set_extension_highlight("ENT", False)
        self._set_extension_highlight("DEL", False)
        now = time.time()
        self.pyth_mode = True
        self.pyth_started_at = now
        self.pyth_arm_until = now + PYTH_ARM_SECONDS
        self.hint.configure(
            text=f"PYTH: prêt dans {PYTH_ARM_SECONDS:.1f}s — placez-vous"
        )
        self.bar.configure(progress_color=BAR_ARM)
        self._set_mode_cb("PYTH")
        self._set_extension_highlight("PYTH", True)
        self._refresh_status()

    def _start_csharp(self):
        """Armement puis copie de la commande C# avant validation immédiate (Enter)."""
        self.selection_mode = False
        self.screenshot_mode = False
        self.cola_mode = False
        self.col_mode = False
        self.cop_mode = False
        self.clicd_mode = False
        self.drg_mode = False
        self.drg_holding = False
        self.ent_mode = False
        self.del_mode = False
        self._cancel_csharp()
        self._stop_voice()
        self._set_extension_highlight("SEL", False)
        self._set_extension_highlight("SHOT", False)
        self._set_extension_highlight("COLA", False)
        self._set_extension_highlight("COL", False)
        self._set_extension_highlight("COP", False)
        self._set_extension_highlight("CLICD", False)
        self._set_extension_highlight("DRG", False)
        self._set_extension_highlight("ENT", False)
        self._set_extension_highlight("DEL", False)
        now = time.time()
        self.csharp_mode = True
        self.csharp_started_at = now
        self.csharp_arm_until = now + PYTH_ARM_SECONDS
        self.hint.configure(
            text=f"CSH#: prêt dans {PYTH_ARM_SECONDS:.1f}s — placez-vous"
        )
        self.bar.configure(progress_color=BAR_ARM)
        self._set_mode_cb("CSHARP")
        self._set_extension_highlight("CSHARP", True)
        self._refresh_status()

    def _start_del(self):
        """Armement puis Ctrl+A / Delete (supprime tout)."""
        self.selection_mode = False
        self.screenshot_mode = False
        self.cola_mode = False
        self.col_mode = False
        self.cop_mode = False
        self.clicd_mode = False
        self.drg_mode = False
        self.drg_holding = False
        self._cancel_pyth()
        self._stop_voice()
        self._set_extension_highlight("SEL", False)
        self._set_extension_highlight("SHOT", False)
        self._set_extension_highlight("COLA", False)
        self._set_extension_highlight("COL", False)
        self._set_extension_highlight("COP", False)
        self._set_extension_highlight("CLICD", False)
        self._set_extension_highlight("DRG", False)
        self._set_extension_highlight("PYTH", False)
        self.del_mode = True
        self.del_started_at = time.time()
        self.del_arm_until = self.del_started_at + DEL_ARM_SECONDS
        self.hint.configure(text=f"DEL: pret dans {rest:.1f}s - placez-vous")
        self.bar.configure(progress_color=BAR_ARM)
        self._set_mode_cb("DEL")
        self._set_extension_highlight("DEL", True)
        self._refresh_status()

    def _start_drg(self):
        """Armement ? immobilité = mouseDown ? tu déplaces ? re-immobilité = mouseUp."""
        self.selection_mode = False
        self.screenshot_mode = False
        self.cola_mode = False
        self.col_mode = False
        self.cop_mode = False
        self.clicd_mode = False
        self._cancel_pyth()
        self._stop_voice()
        self._set_extension_highlight("SEL", False)
        self._set_extension_highlight("SHOT", False)
        self._set_extension_highlight("COLA", False)
        self._set_extension_highlight("COL", False)
        self._set_extension_highlight("COP", False)
        self._set_extension_highlight("CLICD", False)
        self._set_extension_highlight("PYTH", False)
        self._set_extension_highlight("VOICE", False)
        self.drg_mode = True
        self.drg_holding = False
        self.drg_arm_until = time.time() + DRG_ARM_SECONDS
        self.hint.configure(
            text=f"DRG: prêt dans {DRG_ARM_SECONDS:.1f}s — placez-vous sur l’élément à déplacer"
        )
        self.bar.configure(progress_color=BAR_ARM)
        self._set_mode_cb("DRG")
        self._set_extension_highlight("DRG", True)
        self._refresh_status()

    def _start_voice(self):
        self.selection_mode = False
        self.screenshot_mode = False
        self.cola_mode = False
        self.col_mode = False
        self.cop_mode = False
        self.drg_mode = False
        self.drg_holding = False
        self.clicd_mode = False
        self._cancel_pyth()
        self._set_extension_highlight("SEL", False)
        self._set_extension_highlight("SHOT", False)
        self._set_extension_highlight("COLA", False)
        self._set_extension_highlight("COL", False)
        self._set_extension_highlight("COP", False)
        self._set_extension_highlight("DRG", False)
        self._set_extension_highlight("CLICD", False)
        self._set_extension_highlight("PYTH", False)
        self.gpt.toggle()
        self._set_extension_highlight(
            "VOICE", getattr(self.gpt, "enabled", False))
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
            moved = (abs(pos[0] - prev[0]) + abs(pos[1] - prev[1])) > MOVE_EPS
            now = time.time()
            try:
                self._update_scroll_target(pos)
            except Exception:
                pass

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
                    self.hint.configure(
                        text=f"SEL: prêt dans {rest:.1f}s — placez-vous au début du texte"
                    )
                    self.bar.configure(progress_color=BAR_ARM)
                    self.progress_value = max(
                        0.0, min(1.0, 1.0 - rest / max(SEL_ARM_SECONDS, 0.001))
                    )
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
                            log.info(
                                "[APP] SEL: mouseDown @ (%d,%d)", pos[0], pos[1])
                            self.hint.configure(
                                text="SEL: maintiens & déplace. Immobilise pour relâcher + copier"
                            )
                            self.bar.configure(progress_color=BAR_OK)
                            self.selection_phase_down = True
                        except Exception as e:
                            log.exception("SEL mouseDown failed: %s", e)
                    else:
                        try:
                            pyautogui.mouseUp(pos[0], pos[1])
                            log.info("[APP] SEL: mouseUp @ (%d,%d)",
                                     pos[0], pos[1])
                            time.sleep(0.06)
                            kb_copy()
                            log.info("[APP] SEL: copied to clipboard")
                            self.hint.configure(text="SEL: copié ?")
                        except Exception as e:
                            log.exception("SEL finalize failed: %s", e)
                            self.hint.configure(text="SEL: erreur (voir logs)")
                        self.selection_mode = False
                        self._set_extension_highlight("SEL", False)
                        self.selection_phase_down = False
                        self.bar.configure(progress_color=BAR_DEFAULT)
                        self._set_mode_cb("CLICK")
                        self._refresh_status()
                    t0 = now
                    self.progress_value = 0.0
                    time.sleep(0.08)
                time.sleep(0.05)
                continue

            # ------------ SELCP mode ------------
            if self.selcp_mode:
                if now < self.selcp_arm_until:
                    rest = self.selcp_arm_until - now
                    self.hint.configure(
                        text=f"SELCP: prêt dans {rest:.1f}s — placez-vous au début du texte"
                    )
                    self.bar.configure(progress_color=BAR_ARM)
                    self.progress_value = max(
                        0.0, min(1.0, 1.0 - rest / max(SEL_ARM_SECONDS, 0.001))
                    )
                    time.sleep(0.05)
                    prev = pos
                    continue

                if not self.selcp_phase_down:
                    # Démarrage de la sélection : clic gauche
                    pyautogui.mouseDown()
                    self.selcp_phase_down = True
                    self.hint.configure(
                        text="SELCP: déplacez pour sélectionner")
                    self.progress_value = 0.0
                    t0 = now  # reset du timer d'immobilité
                    time.sleep(0.05)
                    prev = pos
                    continue

                # Phase 2 : on suit le mouvement
                if moved:
                    self.progress_value = 0.0
                    t0 = now  # reset du timer
                else:
                    # Pas de mouvement
                    rest = max(0.0, SEL_ARM_SECONDS - (now - t0))
                    if rest > 0:
                        self.progress_value = max(
                            0.0, min(1.0, 1.0 - rest / SEL_ARM_SECONDS)
                        )
                    else:
                        # Fin : souris immobile depuis assez longtemps
                        pyautogui.mouseUp()
                        try:
                            kb_copy()
                            log.info("[APP] SELCP: texte copié")
                            self.hint.configure(text="📋 Texte copié")
                        except Exception as e:
                            log.exception("SELCP finalize failed: %s", e)
                            self.hint.configure(text="❌ Copie échouée")
                        self.selcp_mode = False
                        self._set_extension_highlight("SELCP", False)
                        self.selcp_phase_down = False
                        self.bar.configure(progress_color=BAR_DEFAULT)
                        self._set_mode_cb("CLICK")
                        self._refresh_status()
                        self.progress_value = 0.0
                        time.sleep(0.08)
                time.sleep(0.05)
                prev = pos
                continue

            # ------------ SELDL mode ------------
            if self.seldl_mode:
                if now >= self.seldl_arm_until:
                    if not self.seldl_phase_down:
                        pyautogui.mouseDown()
                        self.seldl_phase_down = True
                        self.hint.configure(
                            text="SELDL: déplacez pour sélectionner"
                        )
                        t0 = now
                        time.sleep(0.05)
                        prev = pos
                        continue
                    else:
                        if moved:
                            t0 = now
                            self.progress_value = 0.0
                        else:
                            rest = SEL_ARM_SECONDS - (now - t0)
                            if rest > 0:
                                self.progress_value = max(
                                    0.0, min(1.0, 1.0 - rest / SEL_ARM_SECONDS)
                                )
                            else:
                                pyautogui.mouseUp()
                                try:
                                    pyautogui.press("delete")
                                    log.info("[APP] SELDL: texte supprimé")
                                    self.hint.configure(
                                        text="🗑️ Texte supprimé")
                                except Exception as e:
                                    log.exception(
                                        "SELDL finalize failed: %s", e)
                                    self.hint.configure(
                                        text="❌ Suppression échouée"
                                    )
                                self.seldl_mode = False
                                self._set_extension_highlight("SELDL", False)
                                self.seldl_phase_down = False
                                self.bar.configure(progress_color=BAR_DEFAULT)
                                self._set_mode_cb("CLICK")
                                self._refresh_status()
                                self.progress_value = 0.0
                                time.sleep(0.08)
                        time.sleep(0.05)
                        prev = pos
                        continue
                else:
                    rest = self.seldl_arm_until - now
                    self.hint.configure(
                        text=f"SELDL: prêt dans {rest:.1f}s — placez-vous au début du texte"
                    )
                    self.bar.configure(progress_color=BAR_ARM)
                    self.progress_value = max(
                        0.0, min(1.0, 1.0 - rest / SEL_ARM_SECONDS)
                    )
                    time.sleep(0.05)
                    prev = pos
                    continue

            # ------------ SHOT mode (rectangulaire en 2 immobilités) ------------
            if self.screenshot_mode:
                if now < self.screenshot_arm_until and not self.screenshot_phase_down:
                    rest = self.screenshot_arm_until - now
                    self.hint.configure(
                        text=f"SHOT: prêt dans {rest:.1f}s — placez-vous"
                    )
                    self.bar.configure(progress_color=BAR_ARM)
                    self.progress_value = max(
                        0.0, min(1.0, 1.0 - rest /
                                 max(SHOT_ARM_SECONDS, 0.001))
                    )
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
                            pyautogui.hotkey("win", "shift", "s")
                            log.info(
                                "[APP] SHOT: Windows snipping tool opened (Win+Shift+S)"
                            )
                            self.hint.configure(
                                text="SHOT: outil de capture ouvert — dessinez la zone à capturer"
                            )
                            self._reset_shot()
                            self._set_mode_cb("CLICK")
                            self._refresh_status()
                        else:
                            if not self.screenshot_phase_down:
                                self.shot_anchor = (pos[0], pos[1])
                                self.screenshot_phase_down = True
                                self.hint.configure(
                                    text="SHOT: lock - deplacez puis immobilisez pour valider"
                                )
                                self.bar.configure(progress_color=BAR_OK)
                                log.info(
                                    "[APP] SHOT: anchor @ (%d,%d)", pos[0], pos[1])
                            else:
                                x1, y1 = self.shot_anchor
                                x2, y2 = pos[0], pos[1]
                                ok, msg = screenshot_to_clipboard(
                                    x1, y1, x2, y2)
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

            # ------------ DEL mode (supprimer tout) ------------
            if self.del_mode:
                if now - self.del_started_at > DEL_TIMEOUT_SECS:
                    self.del_mode = False
                    self._set_extension_highlight("DEL", False)
                    self.bar.configure(progress_color=BAR_DEFAULT)
                    self.hint.configure(text="DEL: delai depasse")
                    self._set_mode_cb("CLICK")
                    self._refresh_status()
                    time.sleep(0.05)
                    continue

                if now < self.del_arm_until:
                    rest = self.del_arm_until - now
                    self.hint.configure(
                        text=f"DEL: pret dans {rest:.1f}s - placez-vous"
                    )
                    self.bar.configure(progress_color=BAR_ARM)
                    self.progress_value = max(
                        0.0, min(1.0, 1.0 - rest / max(DEL_ARM_SECONDS, 0.001))
                    )
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
                        pyautogui.click(pos[0], pos[1])
                        time.sleep(0.06)
                        kb_select_all()
                        time.sleep(0.02)
                        delete_or_backspace()
                        log.info("[APP] DEL: deleted all")
                        self.hint.configure(text="DEL: supprime")
                    except Exception as e:
                        log.exception("DEL failed: %s", e)
                        self.hint.configure(text="DEL: erreur (voir logs)")
                    self.del_mode = False
                    self._set_extension_highlight("DEL", False)
                    self.bar.configure(progress_color=BAR_DEFAULT)
                    self._set_mode_cb("CLICK")
                    self._refresh_status()
                    t0 = now
                    self.progress_value = 0.0
                    time.sleep(0.1)
                time.sleep(0.05)
                continue
            # ------------ COLA mode (remplacement intégral) ------------
            if self.cola_mode:
                if now - self.cola_started_at > COLA_TIMEOUT_SECS:
                    self.cola_mode = False
                    self._set_extension_highlight("COLA", False)
                    self.bar.configure(progress_color=BAR_DEFAULT)
                    self.hint.configure(text="COLA: délai dépassé")
                    self._set_mode_cb("CLICK")
                    self._refresh_status()
                    time.sleep(0.05)
                    continue

                if now < self.cola_arm_until:
                    rest = self.cola_arm_until - now
                    self.hint.configure(
                        text=f"COLA: prêt dans {rest:.1f}s — placez-vous"
                    )
                    self.bar.configure(progress_color=BAR_ARM)
                    self.progress_value = max(
                        0.0, min(1.0, 1.0 - rest /
                                 max(COLA_ARM_SECONDS, 0.001))
                    )
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
                        pyautogui.click(pos[0], pos[1])  # focus
                        time.sleep(0.06)
                        kb_select_all()
                        time.sleep(0.02)
                        delete_or_backspace()
                        time.sleep(0.02)
                        kb_paste()
                        log.info("[APP] COLA: pasted clipboard (full replace)")
                        self.hint.configure(text="COLA: collé ?")
                    except Exception as e:
                        log.exception("COLA failed: %s", e)
                        self.hint.configure(text="COLA: erreur (voir logs)")
                    self.cola_mode = False
                    self._set_extension_highlight("COLA", False)
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
                    self._set_extension_highlight("COL", False)
                    self.bar.configure(progress_color=BAR_DEFAULT)
                    self.hint.configure(text="COL: délai dépassé")
                    self._set_mode_cb("CLICK")
                    self._refresh_status()
                    time.sleep(0.05)
                    continue

                if now < self.col_arm_until:
                    rest = self.col_arm_until - now
                    self.hint.configure(
                        text=f"COL: prêt dans {rest:.1f}s — placez-vous"
                    )
                    self.bar.configure(progress_color=BAR_ARM)
                    self.progress_value = max(
                        0.0, min(1.0, 1.0 - rest / max(COL_ARM_SECONDS, 0.001))
                    )
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
                        pyautogui.click(pos[0], pos[1])  # focus
                        time.sleep(0.06)
                        kb_paste()  # coller uniquement
                        log.info("[APP] COL: pasted clipboard (simple)")
                        self.hint.configure(text="COL: collé ?")
                    except Exception as e:
                        log.exception("COL failed: %s", e)
                        self.hint.configure(text="COL: erreur (voir logs)")
                    self.col_mode = False
                    self._set_extension_highlight("COL", False)
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
                    self._set_extension_highlight("COP", False)
                    self.bar.configure(progress_color=BAR_DEFAULT)
                    self.hint.configure(text="COP: délai dépassé")
                    self._set_mode_cb("CLICK")
                    self._refresh_status()
                    time.sleep(0.05)
                    continue

                if now < self.cop_arm_until:
                    rest = self.cop_arm_until - now
                    self.hint.configure(
                        text=f"COP: prêt dans {rest:.1f}s — placez-vous"
                    )
                    self.bar.configure(progress_color=BAR_ARM)
                    self.progress_value = max(
                        0.0, min(1.0, 1.0 - rest / max(COP_ARM_SECONDS, 0.001))
                    )
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
                        pyautogui.click(pos[0], pos[1])  # focus
                        time.sleep(0.06)
                        kb_copy_all()  # Ctrl+A puis Ctrl+C
                        log.info(
                            "[APP] COP: copied selection (Ctrl+A then Ctrl+C)")
                        self.hint.configure(text="COP: copié ?")
                    except Exception as e:
                        log.exception("COP failed: %s", e)
                        self.hint.configure(text="COP: erreur (voir logs)")
                    self.cop_mode = False
                    self._set_extension_highlight("COP", False)
                    self.bar.configure(progress_color=BAR_DEFAULT)
                    self._set_mode_cb("CLICK")
                    self._refresh_status()
                    t0 = now
                    self.progress_value = 0.0
                    time.sleep(0.1)
                time.sleep(0.05)
                continue

            # ------------ ENT mode (press Enter) ------------
            if self.ent_mode:
                if now - self.ent_started_at > ENT_TIMEOUT_SECS:
                    self.ent_mode = False
                    self._set_extension_highlight("ENT", False)
                    self.bar.configure(progress_color=BAR_DEFAULT)
                    self.hint.configure(text="ENT: délai dépassé")
                    self._set_mode_cb("CLICK")
                    self._refresh_status()
                    time.sleep(0.05)
                    continue

                if now < self.ent_arm_until:
                    rest = self.ent_arm_until - now
                    self.hint.configure(
                        text=f"ENT: prêt dans {rest:.1f}s – placez-vous"
                    )
                    self.bar.configure(progress_color=BAR_ARM)
                    self.progress_value = max(
                        0.0, min(1.0, 1.0 - rest / max(ENT_ARM_SECONDS, 0.001))
                    )
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
                        pyautogui.click(pos[0], pos[1])  # focus
                        time.sleep(0.06)
                        pyautogui.press("enter")  # appuie sur Entrée
                        log.info("[APP] ENT: Enter pressed")
                        self.hint.configure(text="ENT: entrée envoyée")
                    except Exception as e:
                        log.exception("ENT failed: %s", e)
                        self.hint.configure(text="ENT: erreur (voir logs)")
                    self.ent_mode = False
                    self._set_extension_highlight("ENT", False)
                    self.bar.configure(progress_color=BAR_DEFAULT)
                    self._set_mode_cb("CLICK")
                    self._refresh_status()
                    t0 = now
                    self.progress_value = 0.0
                    time.sleep(0.1)
                time.sleep(0.05)
                continue

            # ------------ CSHARP mode (écrire commande C# + Enter) ------------

            if self.csharp_mode:
                if now - self.csharp_started_at > PYTH_TIMEOUT_SECS:
                    self.csharp_mode = False
                    self._set_extension_highlight("CSHARP", False)
                    self.bar.configure(progress_color=BAR_DEFAULT)
                    self.hint.configure(text="CSH#: délai dépassé")
                    self._set_mode_cb("CLICK")
                    self._refresh_status()
                    continue

                if now < self.csharp_arm_until:
                    rest = self.csharp_arm_until - now
                    self.hint.configure(text=f"CSH#: prêt dans {rest:.1f}s")
                    self.bar.configure(progress_color=BAR_ARM)
                    self.progress_value = max(
                        0.0, min(1.0, 1.0 - rest / max(PYTH_ARM_SECONDS, 0.001)))
                    time.sleep(0.05)
                    continue

                try:
                    # Clic pour focus
                    x, y = pyautogui.position()
                    pyautogui.click(x, y)
                    time.sleep(0.05)

                    # Copier la commande dans le presse-papiers
                    kb_copy()
                    time.sleep(1.5)
                    self._set_clipboard_text(self._csharp_command)
                    time.sleep(0.05)

                    # Sélectionner tout + coller
                    kb_select_all()
                    time.sleep(0.05)
                    kb_paste()
                    time.sleep(0.05)

                    # Valider avec Entrée
                    pyautogui.press("enter")
                    log.info("[APP] CSHARP: commande envoyée")
                    self.hint.configure(text="CSH#: commande envoyée")
                except Exception as e:
                    log.exception("CSHARP failed: %s", e)
                    self.hint.configure(text="CSH#: erreur")

                # Réinitialiser
                self.csharp_mode = False
                self._set_extension_highlight("CSHARP", False)
                self.bar.configure(progress_color=BAR_DEFAULT)
                self._set_mode_cb("CLICK")
                self._refresh_status()
                time.sleep(0.1)
                continue

            # ------------ PYTH mode (écrire python main.py + Enter) ------------
            if self.pyth_mode:
                if now - self.pyth_started_at > PYTH_TIMEOUT_SECS:
                    self.pyth_mode = False
                    self._set_extension_highlight("PYTH", False)
                    self.bar.configure(progress_color=BAR_DEFAULT)
                    self.hint.configure(text="PYTH: délai dépassé")
                    self._set_mode_cb("CLICK")
                    self._refresh_status()
                    time.sleep(0.05)
                    continue

                if now < self.pyth_arm_until:
                    rest = self.pyth_arm_until - now
                    self.hint.configure(
                        text=f"PYTH: prêt dans {rest:.1f}s — placez-vous"
                    )
                    self.bar.configure(progress_color=BAR_ARM)
                    self.progress_value = max(
                        0.0, min(1.0, 1.0 - rest /
                                    max(PYTH_ARM_SECONDS, 0.001))
                    )
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
                        pyautogui.click(pos[0], pos[1])
                        time.sleep(0.05)
                        kb_copy()
                        time.sleep(1.5)
                        copied = self._set_clipboard_text(self._pyth_command)
                        time.sleep(0.05)
                        kb_select_all()
                        time.sleep(0.05)
                        if copied:
                            kb_paste()
                        else:
                            pyautogui.write(self._pyth_command)
                        time.sleep(0.05)
                        pyautogui.press("enter")
                        log.info("[APP] PYTH: command executed")
                        self.hint.configure(text="PYTH: commande envoyée")
                    except Exception as e:
                        log.exception("PYTH failed: %s", e)
                        self.hint.configure(text="PYTH: erreur (voir logs)")
                    self.pyth_mode = False
                    self._set_extension_highlight("PYTH", False)
                    self.bar.configure(progress_color=BAR_DEFAULT)
                    self._set_mode_cb("CLICK")
                    self._refresh_status()
                    t0 = now
                    self.progress_value = 0.0
                    time.sleep(0.12)
                time.sleep(0.05)
                continue
# ------------ CSHARP mode (écrire commande C# + Enter) ------------
            if self.csharp_mode:
                if now - self.csharp_started_at > PYTH_TIMEOUT_SECS:
                    self.csharp_mode = False
                    self._set_extension_highlight("CSHARP", False)
                    self.bar.configure(progress_color=BAR_DEFAULT)
                    self.hint.configure(text="CSH#: délai dépassé")
                    self._set_mode_cb("CLICK")
                    self._refresh_status()
                    time.sleep(0.05)
                    continue

                if now < self.csharp_arm_until:
                    rest = self.csharp_arm_until - now
                    self.hint.configure(
                        text=f"CSH#: prêt dans {rest:.1f}s — placez-vous"
                    )
                    self.bar.configure(progress_color=BAR_ARM)
                    self.progress_value = max(
                        0.0, min(1.0, 1.0 - rest / max(PYTH_ARM_SECONDS, 0.001))
                    )
                    time.sleep(0.05)
                    prev = pos
                    continue

                try:
                    # Clic pour focus
                    x, y = pyautogui.position()
                    pyautogui.click(x, y)
                    time.sleep(0.05)

                    # Copier la commande dans le presse-papiers
                    kb_copy()
                    time.sleep(1.5)
                    self._set_clipboard_text(self._csharp_command)
                    time.sleep(0.05)

                    # Sélectionner tout + coller
                    kb_select_all()
                    time.sleep(0.05)
                    kb_paste()
                    time.sleep(0.05)

                    # Valider avec Entrée
                    pyautogui.press("enter")
                    log.info("[APP] CSHARP: commande envoyée")
                    self.hint.configure(text="CSH#: commande envoyée")
                except Exception as e:
                    log.exception("CSHARP failed: %s", e)
                    self.hint.configure(text="CSH#: erreur (voir logs)")

                # Réinitialiser le mode
                self.csharp_mode = False
                self._set_extension_highlight("CSHARP", False)
                self.bar.configure(progress_color=BAR_DEFAULT)
                self._set_mode_cb("CLICK")
                self._refresh_status()
                time.sleep(0.12)
                continue
            
            # ------------ CLICD mode (clic droit sur immobilisation) ------------
            if self.clicd_mode:
                if now - self.clicd_started_at > CLICD_TIMEOUT_SECS:
                    self.clicd_mode = False
                    self._set_extension_highlight("CLICD", False)
                    self.bar.configure(progress_color=BAR_DEFAULT)
                    self.hint.configure(text="CLICD: délai dépassé")
                    self._set_mode_cb("CLICK")
                    self._refresh_status()
                    time.sleep(0.05)
                    continue

                if now < self.clicd_arm_until:
                    rest = self.clicd_arm_until - now
                    self.hint.configure(
                        text=f"CLICD: prêt dans {rest:.1f}s — placez-vous"
                    )
                    self.bar.configure(progress_color=BAR_ARM)
                    self.progress_value = max(
                        0.0, min(1.0, 1.0 - rest /
                                    max(CLICD_ARM_SECONDS, 0.001))
                    )
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
                        pyautogui.click(pos[0], pos[1], button="right")
                        log.info(
                            "[APP] CLICD: right click @ (%d,%d)", pos[0], pos[1])
                        self.hint.configure(text="CLICD: clic droit ?")
                    except Exception as e:
                        log.exception("CLICD failed: %s", e)
                        self.hint.configure(text="CLICD: erreur (voir logs)")
                    self.clicd_mode = False
                    self._set_extension_highlight("CLICD", False)
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
                # Armement initial (tu te places sur la zone à "attraper")
                if not self.drg_holding and now < self.drg_arm_until:
                    rest = self.drg_arm_until - now
                    self.hint.configure(
                        text=f"DRG: prêt dans {rest:.1f}s - placez-vous sur l'élément à déplacer"
                    )
                    self.bar.configure(progress_color=BAR_ARM)
                    self.progress_value = max(
                        0.0, min(1.0, 1.0 - rest / max(DRG_ARM_SECONDS, 0.001))
                    )
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
                        # Cas spécial: si curseur sur un bouton de la toolbar, on initie un drag interne d'extension
                        key_under = self._toolbar_key_at(pos[0], pos[1])
                        if key_under is not None and key_under not in getattr(
                            self, "_mod_of_key", {}
                        ):
                            try:
                                # Crée un fantôme qui suit le curseur
                                ghost = ctk.CTkFrame(
                                    self.root, corner_radius=8)
                                label = ctk.CTkLabel(
                                    ghost, text=self._extensions[key_under]["label"]
                                )
                                label.pack(padx=6, pady=4)
                                rx, ry = (
                                    self.root.winfo_rootx(),
                                    self.root.winfo_rooty(),
                                )
                                gx = max(0, pos[0] - rx + 8)
                                gy = max(0, pos[1] - ry + 8)
                                ghost.place(x=gx, y=gy)
                                try:
                                    ghost.lift()
                                except Exception:
                                    pass
                                self._drag_toolbar_key = key_under
                                self._drag_toolbar_ghost = ghost
                                self.hint.configure(
                                    text="DRG: glissez l’extension hors de la barre, immobilisez pour déposer"
                                )
                                self.bar.configure(progress_color=BAR_OK)
                                self.drg_holding = True
                            except Exception as e:
                                log.exception(
                                    "DRG toolbar start failed: %s", e)
                                self._drag_toolbar_key = None
                                self._drag_toolbar_ghost = None
                                # Fallback: comportement DRG classique
                                try:
                                    pyautogui.mouseDown(pos[0], pos[1])
                                    log.info(
                                        "[APP] DRG: mouseDown @ (%d,%d)", pos[0], pos[1]
                                    )
                                    self.hint.configure(
                                        text="DRG: maintiens & déplace. Immobilise pour relâcher"
                                    )
                                    self.bar.configure(progress_color=BAR_OK)
                                    self.drg_holding = True
                                except Exception as e2:
                                    log.exception(
                                        "DRG mouseDown failed: %s", e2)
                                    self.drg_mode = False
                                    self.drg_holding = False
                                    self._set_extension_highlight("DRG", False)
                                    self.bar.configure(
                                        progress_color=BAR_DEFAULT)
                                    self._set_mode_cb("CLICK")
                                    self._refresh_status()
                        else:
                            # Comportement DRG classique (hors toolbar)
                            try:
                                pyautogui.mouseDown(pos[0], pos[1])
                                log.info(
                                    "[APP] DRG: mouseDown @ (%d,%d)", pos[0], pos[1]
                                )
                                self.hint.configure(
                                    text="DRG: maintiens & déplace. Immobilise pour relâcher"
                                )
                                self.bar.configure(progress_color=BAR_OK)
                                self.drg_holding = True
                            except Exception as e:
                                log.exception("DRG mouseDown failed: %s", e)
                                # en cas d'échec, on sort du mode
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
                    # Si on est en drag interne d’un bouton de toolbar, suivre le curseur et prévisualiser
                    if self._drag_toolbar_key is not None:
                        try:
                            if moved:
                                # déplace le fantôme
                                if (
                                    self._drag_toolbar_ghost is not None
                                    and self._drag_toolbar_ghost.winfo_exists() == 1
                                ):
                                    rx, ry = (
                                        self.root.winfo_rootx(),
                                        self.root.winfo_rooty(),
                                    )
                                    gx = max(0, pos[0] - rx + 8)
                                    gy = max(0, pos[1] - ry + 8)
                                    self._drag_toolbar_ghost.place_configure(
                                        x=gx, y=gy)
                                    try:
                                        self._drag_toolbar_ghost.lift()
                                    except Exception:
                                        pass
                                # aperçu module sous le curseur
                                try:
                                    mod_id = self._find_module_at(
                                        pos[0], pos[1])
                                    if mod_id is not None:
                                        orient = self._decide_drop_orientation(
                                            mod_id, pos[0], pos[1]
                                        )
                                        self._show_module_preview(
                                            mod_id, orient, pos[0], pos[1]
                                        )
                                    else:
                                        self._clear_module_preview()
                                except Exception:
                                    pass
                                prev = pos
                                t0 = now
                                self.progress_value = 0.0
                                time.sleep(0.05)
                                continue
                            # immobilité => déposer
                            elapsed = now - t0
                            ratio = max(
                                0.0, min(elapsed / self.dwell_delay, 1.0))
                            self.progress_value = ratio
                            if ratio >= 1.0:
                                try:
                                    # Dépôt: hors HUD => créer/ajouter à un module; dans shelf => retirer de la barre
                                    bx = self.wrap.winfo_rootx()
                                    by = self.wrap.winfo_rooty()
                                    bw = self.wrap.winfo_width()
                                    bh = self.wrap.winfo_height()
                                    outside = (
                                        (pos[0] < bx)
                                        or (pos[0] > bx + bw)
                                        or (pos[1] < by)
                                        or (pos[1] > by + bh)
                                    )
                                    inside_shelf = False
                                    try:
                                        if getattr(self, "_shelf_visible", False):
                                            sx = self._shelf_row.winfo_rootx()
                                            sy = self._shelf_row.winfo_rooty()
                                            sw = self._shelf_row.winfo_width()
                                            sh = self._shelf_row.winfo_height()
                                            inside_shelf = (
                                                sx <= pos[0] <= sx + sw
                                            ) and (sy <= pos[1] <= sy + sh)
                                    except Exception:
                                        inside_shelf = False
                                    if inside_shelf:
                                        self._remove_one_from_toolbar(
                                            self._drag_toolbar_key
                                        )
                                    elif outside:
                                        self._move_extension_to_floating(
                                            self._drag_toolbar_key, pos[0], pos[1]
                                        )
                                    self.hint.configure(text="DRG: déposé ?")
                                except Exception as e:
                                    log.exception(
                                        "DRG toolbar drop failed: %s", e)
                                    self.hint.configure(
                                        text="DRG: erreur (voir logs)")
                                finally:
                                    self._clear_module_preview()
                                    # nettoyage fantôme
                                    try:
                                        if (
                                            self._drag_toolbar_ghost is not None
                                            and self._drag_toolbar_ghost.winfo_exists()
                                            == 1
                                        ):
                                            self._drag_toolbar_ghost.place_forget()
                                            self._drag_toolbar_ghost.destroy()
                                    except Exception:
                                        pass
                                    self._drag_toolbar_ghost = None
                                    self._drag_toolbar_key = None
                                    # Quitter DRG
                                    self.drg_mode = False
                                    self.drg_holding = False
                                    self._set_extension_highlight("DRG", False)
                                    self.bar.configure(
                                        progress_color=BAR_DEFAULT)
                                    self._set_mode_cb("CLICK")
                                    self._refresh_status()
                                    t0 = now
                                    self.progress_value = 0.0
                                    time.sleep(0.08)
                                time.sleep(0.05)
                                continue
                        except Exception:
                            # En cas d’erreur, retomber sur le comportement standard
                            pass
                    # Comportement DRG standard (pas un drag interne de bouton)
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
                            log.info("[APP] DRG: mouseUp @ (%d,%d)",
                                    pos[0], pos[1])
                            self.hint.configure(text="DRG: relâché ?")
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
                    if self.anchor_point and not inside_deadzone(
                        pos, self.anchor_point, DEADZONE_RADIUS
                    ):
                        self.rearm_in_deadzone = True
                    prev = pos
                    t0 = now
                    self.progress_value = 0.0
                else:
                    elapsed = now - t0
                    ratio = max(0.0, min(elapsed / self.dwell_delay, 1.0))
                    self.progress_value = ratio
                    if ratio >= 1.0:
                        if (
                            (self.anchor_point is None)
                            or (
                                not inside_deadzone(
                                    pos, self.anchor_point, DEADZONE_RADIUS
                                )
                            )
                            or self.rearm_in_deadzone
                        ):
                            try:
                                pyautogui.click(pos[0], pos[1])
                                self.anchor_point = pos
                                self.rearm_in_deadzone = False
                                log.info(
                                    "[APP] auto-click @ (%d,%d)", pos[0], pos[1])
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


# ---------- LANCEMENT EXPLICITE DE L’APPLICATION ----------
if __name__ == "__main__":
    import multiprocessing

    # Important pour PyInstaller sur Windows quand des threads/process peuvent être lancés
    multiprocessing.freeze_support()

    try:
        app = NoClicApp()
        # Assure l'élévation initiale
        app.root.after(300, app.root.lift)
        app.run()
    except Exception as e:
        # Si build --console (debug), on verra la trace.
        import traceback

        traceback.print_exc()
        # Si build --windowed, afficher un message d'erreur visible.
        try:
            import tkinter as tk
            from tkinter import messagebox

            r = tk.Tk()
            r.withdraw()
            r.attributes("-topmost", True)
            messagebox.showerror("NoClic - Erreur", f"{e}")
            r.destroy()
        except Exception:
            pas

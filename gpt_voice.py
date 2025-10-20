# gpt_voice.py — VOICE avec fin sur silence + délai de collage + logs détaillés
import customtkinter as ctk
import logging
import pyautogui
import pyperclip
import sounddevice as sd
import numpy as np
import time
import threading
import io
import os
import json
from pathlib import Path
import soundfile as sf
import sys
import shutil
import tempfile
from pathlib import Path

# === Ajoute cette fonction en haut du fichier, après les imports ===
# Recherche de chemin compatible PyInstaller
def resource_path(relative_path):
    """Retourne le chemin absolu compatible PyInstaller."""
    try:
        base_path = Path(sys._MEIPASS)
    except Exception:
        base_path = Path(__file__).parent
    return base_path / relative_path

def get_model_path():
    """Retourne un chemin vers le modèle, en s'assurant qu'il est accessible, même dans un .exe."""
    model_src = resource_path("models/base")
    model_dest = Path(tempfile.gettempdir()) / "noclic_whisper" / "base"

    # Si on est dans un .exe (PyInstaller)
    if hasattr(sys, '_MEIPASS'):
        # Supprime l’ancien modèle temporaire
        if model_dest.exists():
            shutil.rmtree(model_dest)
        # Crée le dossier parent
        model_dest.parent.mkdir(parents=True, exist_ok=True)
        # Copie le modèle vers un endroit accessible
        shutil.copytree(model_src, model_dest)
        log.info("[VOICE] Modèle copié dans un dossier temporaire : %s", model_dest)
        return str(model_dest)

    # En développement : on utilise le chemin local
    return str(model_src)

# Désactive CUDA par défaut (les erreurs cuDNN venaient de là)
USE_CUDA = False

try:
    from faster_whisper import WhisperModel
except Exception:
    WhisperModel = None

log = logging.getLogger("VOICE")

BAR_DEFAULT = "#1f6aa5"
BAR_WARN = "#f39c12"
BAR_OK = "#27ae60"
BAR_ARM = "#7f8c8d"

# Paramètres audio
AUDIO_SAMPLE_RATE = 16000
AUDIO_CHANNELS = 1
# Durée minimale d'un enregistrement (évite les faux départs)
MIN_REC_TOTAL_SECS = 0.8

# Délai avant collage auto (sera écrasé par settings.json)
DEFAULT_PASTE_DELAY = 2.5

from utils import user_data_path

# Dossier temporaire (peut rester local, car temporaire)
TMP_DIR = Path(tempfile.gettempdir()) / "noclic" / "voice"
TMP_DIR.mkdir(parents=True, exist_ok=True)

# Chemin PERSISTANT pour settings.json
SETTINGS_PATH = user_data_path("settings.json")


def _rms(x: np.ndarray) -> float:
    try:
        return float(np.sqrt(np.mean(np.square(x))))
    except Exception:
        return 0.0


def _load_settings() -> dict:
    d = {}
    try:
        if SETTINGS_PATH.exists():
            with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
                d = json.load(f)
            log.info("[VOICE] settings loaded (%s)", ", ".join(d.keys()))
    except Exception:
        log.exception("settings load failed")
    # Defaults si clefs manquantes
    changed = False
    if "voice_end_silence_secs" not in d:
        d["voice_end_silence_secs"] = 1.6
        changed = True
    if "voice_rms_threshold" not in d:
        d["voice_rms_threshold"] = 0.003
        changed = True
    if "voice_paste_delay_secs" not in d:
        d["voice_paste_delay_secs"] = DEFAULT_PASTE_DELAY
        changed = True
    if changed:
        try:
            with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
                json.dump(d, f, ensure_ascii=False, indent=2)
            log.info("[VOICE] settings defaulted → %s", SETTINGS_PATH.name)
        except Exception:
            log.exception("settings save failed")
    return d


class _Recorder:
    """
    Enregistre en continu et déclenche un auto-stop lorsque
    - une VOIX a été détectée au moins une fois
    - puis on observe `end_silence_secs` de SILENCE consécutif sous `silence_threshold`
    - et la durée totale dépasse `min_total_secs`
    """

    def __init__(
        self,
        samplerate=AUDIO_SAMPLE_RATE,
        channels=AUDIO_CHANNELS,
        device=None,
        silence_threshold=0.003,
        end_silence_secs=1.6,
        min_total_secs=MIN_REC_TOTAL_SECS,
    ):
        self.samplerate = samplerate
        self.channels = channels
        self.device = device

        self.silence_threshold = float(silence_threshold)
        self.end_silence_secs = float(end_silence_secs)
        self.min_total_secs = float(min_total_secs)

        self._frames = []
        self._lock = threading.Lock()
        self._stream = None
        self._recording = False

        self.started_at = 0.0
        self._last_loud_ts = 0.0
        self._had_voice = False
        self._last_report = 0.0

    def _callback(self, indata, frames, time_info, status):
        now = time.time()
        rms = _rms(indata.astype("float32"))
        with self._lock:
            if self._recording:
                self._frames.append(indata.copy())
                if rms >= self.silence_threshold:
                    self._had_voice = True
                    self._last_loud_ts = now

        # log périodique (toutes ~0.4s)
        if now - self._last_report >= 0.4:
            sil = max(0.0, now - (self._last_loud_ts or now))
            log.debug(
                "[REC] frame rms=%.6f thr=%.6f had_voice=%s silence=%.2fs",
                rms,
                self.silence_threshold,
                self._had_voice,
                sil,
            )
            self._last_report = now

    def start(self):
        with self._lock:
            self._frames = []
            self._recording = True
            self.started_at = time.time()
            self._last_loud_ts = self.started_at  # point de départ
            self._had_voice = False
            self._last_report = 0.0

        log.info(
            "[REC] start(samplerate=%d, ch=%d, device=%s, thr=%.4f, end_sil=%.1fs)",
            self.samplerate,
            self.channels,
            str(self.device),
            self.silence_threshold,
            self.end_silence_secs,
        )
        self._stream = sd.InputStream(
            samplerate=self.samplerate,
            channels=self.channels,
            dtype="float32",
            callback=self._callback,
            device=self.device,
        )
        self._stream.start()

    def duration(self) -> float:
        if not self._recording:
            return 0.0
        return max(0.0, time.time() - self.started_at)

    def should_auto_stop(self) -> bool:
        with self._lock:
            if not self._recording:
                return False
            now = time.time()
            dur = now - self.started_at
            if not self._had_voice:
                return False
            sil = now - self._last_loud_ts
            if dur >= self.min_total_secs and sil >= self.end_silence_secs:
                log.info(
                    "[REC] auto-stop (silence %.2fs ≥ %.2fs, dur=%.2fs)",
                    sil,
                    self.end_silence_secs,
                    dur,
                )
                return True
            return False

    def stop_to_wav_bytes(self) -> bytes:
        with self._lock:
            self._recording = False
        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None

        with self._lock:
            if self._frames:
                data = np.concatenate(self._frames, axis=0).astype("float32")
            else:
                data = np.zeros((1, self.channels), dtype="float32")

        maxamp = float(np.max(np.abs(data))) if data.size else 0.0
        if 0 < maxamp < 1e-3:
            gain = min(30.0, 0.03 / maxamp)
            data = (data * gain).astype("float32")
            log.info("[REC] auto-gain x%.1f (maxamp before=%.5f)", gain, maxamp)
        else:
            log.debug("[REC] no gain (maxamp=%.5f)", maxamp)

        dur = data.shape[0] / float(self.samplerate) if self.samplerate else 0.0
        log.info(
            "[REC] stop: frames=%d, samples=%d, duration=%.3fs, last_rms=%.6f",
            len(self._frames),
            data.shape[0],
            dur,
            _rms(data[-min(512, len(data)) :] if len(data) else data),
        )

        with io.BytesIO() as buf:
            sf.write(buf, data, self.samplerate, format="WAV", subtype="PCM_16")
            return buf.getvalue()


class GptVoice:
    def __init__(self, root, parent, hint_label, progress_bar, set_mode_cb):
        self.root = root
        self.parent = parent
        self.hint = hint_label
        self.bar = progress_bar
        self.set_mode_cb = set_mode_cb

        self.enabled = False
        self.recording = False
        self._rec = None
        self._text_pending = False
        self._paste_arm_until = 0.0
        self._device_index = None
        self._model = None
        self._loading_model = False
        self._devices_map = {}

        self._picker_visible = False
        self._picker_delta_h = 36
        self._last_added_h = 0

        # ---- UI: picker SOUS la barre bleue ----
        self._picker_row = ctk.CTkFrame(self.parent, fg_color="transparent")
        self._picker_lbl = ctk.CTkLabel(self._picker_row, text="🎤 Micro :", width=70)
        self._picker_lbl.pack(side="left", padx=(6, 6), pady=(2, 6))
        self._device_var = ctk.StringVar(value="(choisir…)")
        self._device_menu = ctk.CTkOptionMenu(
            self._picker_row,
            variable=self._device_var,
            values=["(scan en cours)"],
            command=self._on_select_device,
            width=280,
        )
        self._device_menu.pack(
            side="left", fill="x", expand=True, padx=(0, 8), pady=(2, 6)
        )
        self._picker_row.pack_forget()

        # settings
        self._settings = _load_settings()
        self._end_silence_secs = float(
            self._settings.get("voice_end_silence_secs", 1.6)
        )
        self._silence_rms_thr = float(self._settings.get("voice_rms_threshold", 0.003))
        self._paste_delay_secs = float(
            self._settings.get("voice_paste_delay_secs", DEFAULT_PASTE_DELAY)
        )

    def _merge_and_save_settings(self, updates: dict) -> None:
        """
        Merge voice-specific updates into the shared settings file without
        dropping keys written by the main application.
        """
        merged = {}
        try:
            if SETTINGS_PATH.exists():
                with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
                    merged = json.load(f)
        except Exception:
            merged = {}
            log.exception("settings reload failed")

        current = dict(self._settings or {})
        for key, value in current.items():
            merged.setdefault(key, value)

        merged.update(updates)
        self._settings = merged
        try:
            with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
                json.dump(merged, f, ensure_ascii=False, indent=2)
            log.info("[VOICE] settings saved -> %s", SETTINGS_PATH.name)
        except Exception:
            log.exception("settings save failed")

    # ---------- PUBLIC ----------
    def toggle(self):
        if not self.enabled:
            self.enabled = True
            self.recording = False
            self._text_pending = False
            self._paste_arm_until = 0.0

            self._refresh_devices()
            self._show_picker()

            self._set_hint(
                "VOICE: choisis ton micro ci-dessous (mémorisé si dispo), puis immobilise pour démarrer 🎙️"
            )
            self._bar_color(BAR_ARM)
            self._set_mode("VOICE")
            log.info("[VOICE] enable")
            self._ensure_model_async()
        else:
            self.stop()

    def stop(self):
        if self.recording and self._rec:
            try:
                self._rec.stop_to_wav_bytes()
            except Exception:
                pass

        self.enabled = False
        self.recording = False
        self._text_pending = False
        self._paste_arm_until = 0.0

        self._hide_picker()

        self._set_hint("")
        self._bar_color(BAR_DEFAULT)
        self._set_mode("CLICK")
        log.info("[VOICE] disable")

    def on_idle(self, now, pos):
        """
        Boucle appelée en permanence par l'app. On retourne True pour empêcher
        l’auto-click générique lorsqu’on est en train d’enregistrer ou qu’un collage est armé.
        """
        if not self.enabled:
            return False

        # Collage auto si un texte est prêt
        if (
            self._text_pending
            and self._paste_arm_until > 0
            and now >= self._paste_arm_until
        ):
            try:
                log.info("[VOICE] paste start (len=%d)", len(pyperclip.paste() or ""))
                pyautogui.click(pos[0], pos[1])
                time.sleep(0.08)
                pyautogui.hotkey("ctrl", "v")
                self._set_hint("VOICE: collé ✓")
                log.info("[VOICE] paste done")
            except Exception:
                self._set_hint("VOICE: erreur collage (voir logs)")
                log.exception("paste failed")
            finally:
                self._text_pending = False
                self._paste_arm_until = 0.0
                self.stop()
            return True

        # Tant que le micro n'est pas choisi → ne consomme pas le dwell (pour que tu puisses cliquer le menu)
        if self._device_index is None and not self.recording and not self._text_pending:
            return False

        # Si on est déjà en enregistrement → on ne stoppe PLUS au dwell.
        if self.recording and self._rec:
            # On consomme le dwell pour éviter les auto-clicks intempestifs pendant que tu parles
            if self._rec.should_auto_stop():
                return self._stop_and_transcribe(now)
            return True

        # Démarrage de l'enregistrement au premier immobilise
        if not self.recording and self._device_index is not None:
            try:
                log.info("[VOICE] start rec (device=%s)", str(self._device_index))
                self._rec = _Recorder(
                    device=self._device_index,
                    silence_threshold=self._silence_rms_thr,
                    end_silence_secs=self._end_silence_secs,
                    min_total_secs=MIN_REC_TOTAL_SECS,
                )
                self._rec.start()
                self.recording = True
                self._set_hint("🎙️ Enregistrement… (arrêt auto après silence)")
                self._bar_color(BAR_OK)
                self._set_mode("VOICE")
            except Exception:
                self._set_hint("VOICE: impossible de démarrer le micro (voir logs)")
                log.exception("start recording failed")
            return True

        return True  # VOICE actif → on consomme le dwell

    def _stop_and_transcribe(self, now) -> bool:
        try:
            self._set_hint("VOICE: transcription en cours…")
            wav_bytes = self._rec.stop_to_wav_bytes()
            self.recording = False

            ts = int(now * 1000)
            tmp_path = TMP_DIR / f"voice_{ts}.wav"
            with open(tmp_path, "wb") as f:
                f.write(wav_bytes)
            size = tmp_path.stat().st_size
            log.info("[VOICE] tmp wav: %s (%.1f KB)", str(tmp_path), size / 1024.0)

            text = self._run_transcribe(str(tmp_path))
            try:
                os.remove(tmp_path)
                log.info("[VOICE] tmp wav removed")
            except Exception:
                log.warning("[VOICE] tmp wav remove failed")

            text = (text or "").strip()
            log.info("[VOICE] transcription done: len=%d chars", len(text))
            if len(text) > 0:
                preview = text[:120].replace("\n", " ")
                if len(text) > 120:
                    preview += "…"
                log.info("[VOICE] text preview: %s", preview)

                pyperclip.copy(text)
                self._set_hint(
                    f"VOICE: texte copié ✓ — collage auto dans {self._paste_delay_secs:.1f}s"
                )
                self._text_pending = True
                self._paste_arm_until = time.time() + self._paste_delay_secs
                self._bar_color(BAR_WARN)
            else:
                self._set_hint("VOICE: (transcription vide)")
                log.warning("[VOICE] transcription empty")
                self._bar_color(BAR_ARM)
            return True

        except Exception:
            self._set_hint("VOICE: erreur transcription (voir logs)")
            log.exception("transcription failed")
            self._bar_color(BAR_ARM)
            return True

    def update_progress(self, now):
        if (
            self.enabled
            and self._text_pending
            and self._paste_arm_until > 0
            and now < self._paste_arm_until
        ):
            rest = max(0.0, self._paste_arm_until - now)
            self._set_hint(f"VOICE: collage auto dans {rest:.1f}s — place-toi")
            self._bar_color(BAR_WARN)

    # ---------- Picker show/hide + devices ----------
    def _show_picker(self):
        if self._picker_visible:
            return
        try:
            self._picker_row.pack(after=self.bar, fill="x", padx=4, pady=(4, 6))
        except Exception:
            self._picker_row.pack(fill="x", padx=4, pady=(4, 6))

        try:
            self.root.update_idletasks()
            w = self.root.winfo_width()
            h = self.root.winfo_height()
            dh = self._picker_delta_h
            self.root.geometry(
                f"{w}x{h+dh}+{self.root.winfo_x()}+{self.root.winfo_y()}"
            )
            self._last_added_h = dh
            log.info("[VOICE] picker show (+%dpx)", dh)
        except Exception:
            log.info("[VOICE] picker show (no size info)")
        self._picker_visible = True

    def _hide_picker(self):
        if not self._picker_visible:
            return
        try:
            self._picker_row.pack_forget()
        except Exception:
            pass
        try:
            self.root.update_idletasks()
            w = self.root.winfo_width()
            h = self.root.winfo_height()
            dh = self._last_added_h
            if dh > 0 and h - dh > 80:
                self.root.geometry(
                    f"{w}x{h-dh}+{self.root.winfo_x()}+{self.root.winfo_y()}"
                )
            log.info("[VOICE] picker hide (restore height)")
        except Exception:
            pass
        self._last_added_h = 0
        self._picker_visible = False

    def _refresh_devices(self):
        """Scanne les devices, remplit le menu et pré-sélectionne celui mémorisé si présent."""
        try:
            log.info("[VOICE] refresh devices ...")
            devices = sd.query_devices()
            inputs, self._devices_map = [], {}

            for idx, d in enumerate(devices):
                if d.get("max_input_channels", 0) > 0:
                    name = f"{d.get('name','?')} (id:{idx})"
                    inputs.append(name)
                    self._devices_map[name] = idx

            log.info("[VOICE] found %d input device(s)", len(inputs))
            if not inputs:
                inputs = ["(aucun micro trouvé)"]
                self._device_index = None
                self._device_var.set(inputs[0])
                self._device_menu.configure(state="disabled", values=inputs)
                return

            self._device_menu.configure(state="normal", values=["(choisir…)"] + inputs)

            remembered = (self._settings or {}).get("voice_device_name")
            if remembered and remembered in self._devices_map:
                self._device_var.set(remembered)
                self._device_index = self._devices_map[remembered]
                log.info(
                    "[VOICE] remembered device restored → %s (idx=%d)",
                    remembered,
                    self._device_index,
                )
                self._set_hint("VOICE: micro mémorisé — immobilise pour enregistrer")
            else:
                self._device_index = None
                self._device_var.set("(choisir…)")
                if remembered:
                    log.info(
                        "[VOICE] remembered device not found on system: %s", remembered
                    )

        except Exception as e:
            self._device_menu.configure(values=[f"Erreur devices: {e}"])
            self._device_index = None
            log.exception("device refresh failed")

    def _on_select_device(self, choice):
        if choice == "(choisir…)" or not hasattr(self, "_devices_map"):
            self._device_index = None
            return
        if choice in self._devices_map:
            self._device_index = self._devices_map[choice]
            log.info("[VOICE] device -> %s (idx=%d)", choice, self._device_index)
            self._set_hint("VOICE: micro sélectionné — immobilise pour enregistrer")
            # Mémoriser
            self._merge_and_save_settings({"voice_device_name": choice})

    # ---------- Transcription ----------
    def _ensure_model_async(self):
        if self._model or self._loading_model:
            return
        self._loading_model = True

        def _load():
            try:
                if WhisperModel is None:
                    raise RuntimeError("faster-whisper non installé")

                # ✅ On utilise get_model_path() au lieu de resource_path direct
                model_path = get_model_path()
                log.info("[VOICE] Chemin du modèle : %s", model_path)

                # Vérifie que le dossier existe et contient les fichiers
                if not os.path.exists(model_path):
                    log.error("[VOICE] Dossier modèle introuvable !")
                    self._model = None
                    return

                log.info("[VOICE] Contenu du dossier modèle : %s", os.listdir(model_path))

                self._model = WhisperModel(
                    model_path,
                    device="cpu",
                    compute_type="int8"
                )
                log.info("[VOICE] Modèle chargé depuis 'models/base' ✅")
            except Exception:
                log.exception("Échec du chargement du modèle embarqué")
                self._model = None
            finally:
                self._loading_model = False

        threading.Thread(target=_load, daemon=True).start()
 
    def _run_transcribe(self, wav_path: str) -> str:
        start = time.time()

        # Si le modèle n'est pas chargé, on tente de le charger (au cas où)
        if not self._model:
            try:
                model_path = get_model_path()
                log.info("[VOICE] Chargement du modèle pour transcription : %s", model_path)
                self._model = WhisperModel(
                    model_path,
                    device="cpu",
                    compute_type="int8"
                )
            except Exception:
                log.exception("Échec du chargement du modèle (run_transcribe)")
                return ""

        log.info("[VOICE] Transcription en cours...")
        try:
            segments, info = self._model.transcribe(
                wav_path,
                language="fr",
                vad_filter=True
            )
            text = " ".join(seg.text for seg in segments).strip()
            elapsed = time.time() - start
            try:
                lang = getattr(info, "language", "?")
                lp = getattr(info, "language_probability", 0.0)
                dur = getattr(info, "duration", 0.0)
                log.info("[VOICE] Transcription : dur=%.2fs, lang=%s (p=%.2f), time=%.2fs",
                        dur, lang, lp, elapsed)
            except Exception:
                log.info("[VOICE] Transcription terminée en %.2fs", elapsed)
            return text
        except Exception:
            log.exception("Échec de la transcription")
            return ""

    # ---------- helpers UI ----------
    def _set_hint(self, text: str):
        try:
            self.hint.configure(text=text)
        except Exception:
            pass

    def _bar_color(self, color: str):
        try:
            self.bar.configure(progress_color=color)
        except Exception:
            pass

    def _set_mode(self, mode_text: str):
        try:
            self.set_mode_cb(mode_text)
        except Exception:
            pass

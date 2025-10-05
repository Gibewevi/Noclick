# config.py — constantes et réglages

# ================== PARAMÈTRES VISUELS ==================
HUD_W            = 560
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

# ================== PARAMÈTRES LOGIQUES ==================
USE_OS_SNIPPER    = False      # True => Win+Shift+S (copie gérée par l'OS)
SHOT_ARM_SECONDS  = 2.0
SEL_ARM_SECONDS   = 1.0

# --- NOUVEAU DÉCOUPAGE ---
# COL  : coller simple (sans Ctrl+A / suppression)
# COLA : coller en remplaçant tout (Ctrl+A -> Delete/Backspace -> Ctrl+V)
COL_ARM_SECONDS   = 0.8
COL_TIMEOUT_SECS  = 5.0

COLA_ARM_SECONDS  = 0.8
COLA_TIMEOUT_SECS = 5.0

DWELL_DELAY_INIT  = 0.7
DEADZONE_RADIUS   = 28
MOVE_EPS          = 2

# Retries clipboard (simples, rapides)
CLIP_OPEN_RETRIES = 40
CLIP_VERIFY_TRIES = 20

# === COP (copie intégrale) : même logique de tempo que COL (réglable séparément si besoin) ===
COP_ARM_SECONDS   = COL_ARM_SECONDS
COP_TIMEOUT_SECS  = COL_TIMEOUT_SECS

# === DRG (drag maintenu) : armement avant mouseDown; release sur re-immobilité ===
# On reprend le même temps d'armement que la sélection par défaut (modifiable).
DRG_ARM_SECONDS   = SEL_ARM_SECONDS

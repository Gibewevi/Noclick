# download_base.py — Télécharge et convertit le modèle 'base' avec logs
from faster_whisper import WhisperModel
import logging

# Active les logs pour voir la progression
logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")

print("🔧 Démarrage du chargement du modèle 'base' (CPU, int8)...")
print("💡 Cela va télécharger (~147 Mo) et convertir le modèle si nécessaire.")

try:
    model = WhisperModel(
        "base",
        device="cpu",
        compute_type="int8"
    )
    print("✅ Modèle chargé avec succès !")
    print("   → Il est maintenant dans ~/.cache/faster_whisper/base")
except Exception as e:
    print("❌ Échec du chargement du modèle :")
    print(e)
# test_download.py — Teste le téléchargement du modèle Whisper 'base'

from faster_whisper import WhisperModel
import logging

# Active les logs pour voir ce qui se passe
logging.basicConfig(level=logging.INFO)
logging.getLogger("urllib3").setLevel(logging.WARNING)
logging.getLogger("huggingface_hub").setLevel(logging.INFO)

print("🔍 Chargement du modèle 'base' (CPU, int8)...")
print("💡 Cela va le télécharger s'il n'est pas déjà présent.")

try:
    model = WhisperModel(
        "base",
        device="cpu",
        compute_type="int8"
    )
    print("✅ Modèle chargé avec succès !")
except Exception as e:
    print("❌ Échec du chargement du modèle :")
    print(e)
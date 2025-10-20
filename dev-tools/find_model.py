# find_model.py — Trouve où faster-whisper a téléchargé (ou tenté de télécharger) le modèle

from huggingface_hub import snapshot_download
from huggingface_hub.utils import GatedRepoError, RepositoryNotFoundError
import os

print("🔍 Recherche du dossier local du modèle 'openai/whisper-base'")

try:
    # On tente de localiser le modèle via le cache de huggingface
    snapshot_folder = snapshot_download(
        repo_id="openai/whisper-base",
        allow_patterns=["*.bin", "config.json", "tokenizer.json"]
    )
    print("✅ Modèle trouvé dans le cache Hugging Face !")
    print(f"📁 Chemin complet : {snapshot_folder}")
    
    # Liste les fichiers
    print("\n📄 Fichiers téléchargés :")
    for root, dirs, files in os.walk(snapshot_folder):
        for file in files:
            print(f"  - {file}")

except RepositoryNotFoundError:
    print("❌ ERREUR : Le modèle 'openai/whisper-base' n'existe pas sur Hugging Face.")
    print("   → Ce devrait être 'distil-whisper/distil-small.en' ou similaire ?")

except Exception as e:
    print(f"❌ Une erreur inattendue s'est produite : {e}")
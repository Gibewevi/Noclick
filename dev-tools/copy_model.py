# copy_model.py — Copie le modèle depuis le cache vers ./models/base

import os
import shutil

# Chemins
cache_dir = os.path.expanduser("~/.cache/faster_whisper/base")
dest_dir = "models/base"

print(f"🔍 Recherche du modèle ici :\n   {cache_dir}")

if not os.path.exists(cache_dir):
    print("❌ Le modèle n'existe pas encore dans le cache.")
    print("   Lance d'abord :")
    print("   python -c \"from faster_whisper import WhisperModel; model = WhisperModel('base', device='cpu', compute_type='int8')\"")
else:
    print(f"✅ Modèle trouvé !")
    print(f"📁 Copie vers :\n   {dest_dir}")

    # Supprime l'ancien dossier s'il existe
    if os.path.exists(dest_dir):
        shutil.rmtree(dest_dir)
        print("🗑️ Ancien dossier supprimé")

    # Copie le modèle
    shutil.copytree(cache_dir, dest_dir)
    print("✅ Modèle copié dans 'models/base' — prêt pour le build !")
# copy_hf_model.py — Copie le modèle Hugging Face vers ./models/base

import os
import shutil

# Chemin source : cache Hugging Face
source_dir = r"C:\Users\pixel\.cache\huggingface\hub\models--openai--whisper-base"

# On cherche le dossier "snapshots" et on prend le premier sous-dossier (le snapshot ID)
snapshot_dir = os.path.join(source_dir, "snapshots")
if not os.path.exists(snapshot_dir):
    print("❌ Dossier snapshots non trouvé :")
    print(snapshot_dir)
    exit(1)

# Liste les dossiers dans snapshots (normalement un seul)
try:
    snapshot_id = os.listdir(snapshot_dir)[0]
    model_source = os.path.join(snapshot_dir, snapshot_id)
    print(f"✅ Dernière version trouvée : {snapshot_id}")
except Exception as e:
    print("❌ Impossible de lire le snapshot :")
    print(e)
    exit(1)

# Dossier destination
model_dest = "models/base"

# Supprime l'ancien dossier si présent
if os.path.exists(model_dest):
    print("🗑️ Suppression ancien modèle...")
    shutil.rmtree(model_dest)

# Copie
print("📁 Copie en cours vers 'models/base'...")
try:
    shutil.copytree(model_source, model_dest)
    print("✅ Modèle copié avec succès !")
    print("🔧 Tu peux maintenant compiler avec PyInstaller.")
except Exception as e:
    print("❌ Échec de la copie :")
    print(e)
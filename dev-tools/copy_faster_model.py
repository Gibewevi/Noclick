# copy_faster_model.py
import os
import shutil

source = os.path.expanduser("~/.cache/faster_whisper/base")
dest = "models/base"

if os.path.exists(source):
    if os.path.exists(dest):
        shutil.rmtree(dest)
    shutil.copytree(source, dest)
    print("✅ Modèle 'base' (faster-whisper) copié dans models/base")
else:
    print("❌ Modèle non trouvé dans ~/.cache/faster_whisper/base")
    print("   → Lance d'abord :")
    print("   python -c \"from faster_whisper import WhisperModel; model = WhisperModel('base', device='cpu', compute_type='int8')\"")
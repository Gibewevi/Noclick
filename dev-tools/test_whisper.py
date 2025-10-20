import sounddevice as sd
import numpy as np
import tempfile
import openai
import os
import wave

# ⚠️ Mets ta clé API OpenAI ici ou exporte-la comme variable d’environnement
openai.api_key = os.getenv("OPENAI_API_KEY") or "TA_CLE_API_ICI"

def record_to_wav(filename, duration=5, samplerate=44100):
    print("🎤 Parle pendant", duration, "secondes...")
    recording = sd.rec(int(duration * samplerate), samplerate=samplerate, channels=1, dtype='int16')
    sd.wait()

    # Sauvegarde en WAV
    with wave.open(filename, 'wb') as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)  # 16 bits
        wf.setframerate(samplerate)
        wf.writeframes(recording.tobytes())
    print("✅ Enregistrement sauvegardé dans", filename)

# fichier temporaire
with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmpfile:
    wav_path = tmpfile.name

record_to_wav(wav_path, duration=5)

# envoi à Whisper
with open(wav_path, "rb") as audio_file:
    transcript = openai.audio.transcriptions.create(
        model="gpt-4o-transcribe", 
        file=audio_file
    )

print("📝 Transcription :", transcript.text)




import sounddevice as sd
import numpy as np

print("🎤 Test micro : Parle pendant 3 secondes...")

# enregistre 3s en mono (1 canal), 44.1 kHz
duration = 3  
samplerate = 44100  
recording = sd.rec(int(duration * samplerate), samplerate=samplerate, channels=1, dtype='float64')
sd.wait()

print("✅ Enregistrement terminé. Taille du buffer :", recording.shape)
print("Quelques échantillons :", recording[:10].flatten())

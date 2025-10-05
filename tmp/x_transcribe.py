
import sys
from faster_whisper import WhisperModel
def main():
    device   = sys.argv[1]
    compute  = sys.argv[2]
    wav_path = sys.argv[3]
    try:
        model = WhisperModel("base", device=device, compute_type=compute)
        # VAD off (plus stable), langue forcée FR (ajuste si besoin)
        segments, _ = model.transcribe(wav_path, language="fr", vad_filter=False)
        text = " ".join(seg.text for seg in segments).strip()
        print("OK::" + text)
    except Exception as e:
        print("ERR::" + str(e))
        sys.exit(1)
if __name__ == "__main__":
    main()

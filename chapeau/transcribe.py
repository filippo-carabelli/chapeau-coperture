"""Trascrizione con Whisper (versione gratuita o se Resolve non ha la trascrizione).

Su Mac Apple Silicon usa mlx-whisper (veloce, usa la GPU); altrove faster-whisper.
"""
from .core import is_apple_silicon, load_config

MLX_MODELS = {"large-v3-turbo": "mlx-community/whisper-large-v3-turbo",
              "small": "mlx-community/whisper-small-mlx",
              "medium": "mlx-community/whisper-medium-mlx"}


def transcribe(audio_path, language="it"):
    cfg = load_config()
    model = (cfg.get("whisper") or {}).get("modello", "large-v3-turbo")
    engine = (cfg.get("whisper") or {}).get("motore") or ("mlx" if is_apple_silicon() else "faster")
    segments = []
    if engine == "mlx":
        import mlx_whisper
        r = mlx_whisper.transcribe(str(audio_path), path_or_hf_repo=MLX_MODELS.get(model, model),
                                   language=language, condition_on_previous_text=False)
        for s in r["segments"]:
            segments.append({"start": round(s["start"], 2), "end": round(s["end"], 2), "text": s["text"].strip()})
    else:
        from faster_whisper import WhisperModel
        wm = WhisperModel(model, device="auto", compute_type="int8")
        it, _ = wm.transcribe(str(audio_path), language=language, vad_filter=True)
        for s in it:
            segments.append({"start": round(s.start, 2), "end": round(s.end, 2), "text": s.text.strip()})
    return {"language": language, "segments": [s for s in segments if s["text"]], "fonte": f"whisper-{engine}"}

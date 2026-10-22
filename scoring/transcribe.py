"""Speech-to-text with faster-whisper (runs locally, no API key needed)."""

import math

_models = {}


def transcribe(wav, model_size="small", language=None):
    """Returns (segments, mean_confidence).

    segments: [{"start": s, "end": s, "text": str}]. mean_confidence is 0-1, derived
    from Whisper's average log-probability; low values suggest poor audio.
    """
    from faster_whisper import WhisperModel

    if model_size not in _models:
        _models[model_size] = WhisperModel(model_size, device="auto", compute_type="int8")
    raw, _info = _models[model_size].transcribe(str(wav), language=language, vad_filter=True)

    segments, logprobs = [], []
    for seg in raw:
        segments.append({"start": seg.start, "end": seg.end, "text": seg.text.strip()})
        logprobs.append(seg.avg_logprob)
    confidence = math.exp(sum(logprobs) / len(logprobs)) if logprobs else 0.0
    return segments, confidence


def parse_transcript_file(text):
    """Accept an uploaded .srt / .vtt / plain-text transcript instead of running Whisper."""
    segments = []
    lines = [l.strip() for l in text.splitlines()]
    i = 0
    while i < len(lines):
        line = lines[i]
        if "-->" in line:
            start = _parse_ts(line.split("-->")[0])
            end = _parse_ts(line.split("-->")[1].split()[0])
            i += 1
            body = []
            while i < len(lines) and lines[i]:
                body.append(lines[i])
                i += 1
            segments.append({"start": start, "end": end, "text": " ".join(body)})
        i += 1
    if not segments:  # plain text, no timestamps
        segments = [{"start": 0.0, "end": 0.0, "text": l} for l in lines if l]
    return segments


def _parse_ts(ts):
    parts = ts.strip().replace(",", ".").split(":")
    seconds = 0.0
    for p in parts:
        seconds = seconds * 60 + float(p)
    return seconds

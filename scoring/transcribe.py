"""Speech-to-text: locally with faster-whisper, through a Whisper API (OpenAI, Groq, ...),
or by letting Gemini listen to the audio."""

import math
import os

_models = {}

# Transcription APIs recognised from the key, with their default models. "whisper" providers use the
# /audio/transcriptions endpoint (any other OpenAI-compatible one works with a base URL); "chat"
# providers get the audio in a chat request and write the transcript themselves.
API_PROVIDERS = {
    "OpenAI": {"model": "whisper-1", "base_url": None, "env_var": "OPENAI_API_KEY", "kind": "whisper"},
    "Groq": {"model": "whisper-large-v3", "base_url": "https://api.groq.com/openai/v1",
             "env_var": "GROQ_API_KEY", "kind": "whisper"},
    "Google Gemini": {"model": "gemini-2.5-flash", "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
                      "env_var": "GEMINI_API_KEY", "kind": "chat"},
}

# Audio chunk length per kind: Whisper APIs take 20 minutes (~5 MB) easily; a chat model writes the
# transcript as output tokens, so shorter chunks keep each answer well under its output limit.
CHUNK_SECONDS = {"whisper": 1200, "chat": 600}

CHAT_SCHEMA = {
    "type": "object",
    "properties": {
        "segments": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "start": {"type": "number"},
                    "end": {"type": "number"},
                    "text": {"type": "string"},
                },
                "required": ["start", "end", "text"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["segments"],
    "additionalProperties": False,
}

CHAT_PROMPT = """Transcribe this audio from an online chess class for kids, word for word, in the language spoken.
Split it into segments of one or two sentences. For each segment give start and end as seconds from
the beginning of this audio clip, and the text. Write chess moves the way they are spoken.
Skip silence and music. If nobody speaks, return an empty list."""


def api_kind(provider):
    return API_PROVIDERS.get(provider, {}).get("kind", "whisper")


def _confidence(logprobs):
    return math.exp(sum(logprobs) / len(logprobs)) if logprobs else 0.0


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
    return segments, _confidence(logprobs)


def transcribe_api(chunks, api_key, model, base_url=None, provider=None):
    """chunks: [(offset_seconds, audio_path)] from media.extract_audio_chunks.

    Returns (segments, mean_confidence) like transcribe(). Confidence comes from the segments'
    avg_logprob when the API reports it, else 1.0 so audio clarity isn't penalised.
    """
    if api_kind(provider) == "chat":
        return transcribe_chat(chunks, api_key, model, base_url), 1.0
    import openai

    client = openai.OpenAI(api_key=api_key or os.environ.get("OPENAI_API_KEY"), base_url=base_url)
    segments, logprobs = [], []
    for offset, path in chunks:
        with open(path, "rb") as f:
            result = client.audio.transcriptions.create(model=model, file=f, response_format="verbose_json")
        raw = _field(result, "segments") or []
        for seg in raw:
            segments.append({"start": offset + _field(seg, "start"), "end": offset + _field(seg, "end"),
                             "text": _field(seg, "text").strip()})
            if _field(seg, "avg_logprob") is not None:
                logprobs.append(_field(seg, "avg_logprob"))
        if not raw and (_field(result, "text") or "").strip():  # API gave text without timestamps
            segments.append({"start": offset, "end": offset, "text": _field(result, "text").strip()})
    return segments, _confidence(logprobs) if logprobs else 1.0


def transcribe_chat(chunks, api_key, model, base_url):
    """Send each audio chunk to an audio-capable chat model (Gemini) and collect its timestamped transcript."""
    from scoring.llm import OpenAICompatibleClient, audio, text

    client = OpenAICompatibleClient(api_key, model, base_url)
    segments = []
    for offset, path in chunks:
        answer = client.ask_json([audio(path.read_bytes(), "mp3"), text(CHAT_PROMPT)], CHAT_SCHEMA, effort="low")
        for seg in answer["segments"]:
            if seg["text"].strip():
                segments.append({"start": offset + seg["start"], "end": offset + seg["end"],
                                 "text": seg["text"].strip()})
    return segments


def _field(obj, name):
    return obj.get(name) if isinstance(obj, dict) else getattr(obj, name, None)


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

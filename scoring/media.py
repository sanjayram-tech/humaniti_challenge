"""Extract audio and sample frames from a class recording with ffmpeg."""

import json
import subprocess
from pathlib import Path


def duration_seconds(video):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", str(video)],
        capture_output=True, text=True, check=True,
    )
    return float(json.loads(out.stdout)["format"]["duration"])


def extract_audio(video, out_dir):
    """16 kHz mono WAV, the format Whisper expects."""
    wav = Path(out_dir) / "audio.wav"
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-i", str(video), "-vn", "-ac", "1", "-ar", "16000", str(wav)],
        check=True,
    )
    return wav


def sample_frames(video, out_dir, every_s=30, max_frames=120, width=640):
    """Grab one JPEG every `every_s` seconds (spread out further if that exceeds max_frames).

    Returns [(timestamp_seconds, path), ...].
    """
    length = duration_seconds(video)
    step = max(every_s, length / max_frames)
    frames_dir = Path(out_dir) / "frames"
    frames_dir.mkdir(parents=True, exist_ok=True)

    frames = []
    t = min(5.0, length / 2)  # skip the very first frames, often black while the call connects
    while t < length:
        path = frames_dir / f"frame_{int(t):06d}.jpg"
        subprocess.run(
            ["ffmpeg", "-y", "-v", "error", "-ss", f"{t:.2f}", "-i", str(video),
             "-frames:v", "1", "-vf", f"scale={width}:-2", "-q:v", "4", str(path)],
            check=True,
        )
        if path.exists():
            frames.append((t, path))
        t += step
    return frames


def fmt_ts(seconds):
    seconds = int(seconds)
    return f"{seconds // 3600:02d}:{seconds % 3600 // 60:02d}:{seconds % 60:02d}"

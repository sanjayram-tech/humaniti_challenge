"""Extract audio and sample frames from a class recording with ffmpeg."""

import re
import shutil
import subprocess
from functools import lru_cache
from pathlib import Path


@lru_cache(maxsize=None)
def ffmpeg_exe():
    """ffmpeg from PATH, else the binary bundled with the imageio-ffmpeg package."""
    exe = shutil.which("ffmpeg")
    if exe:
        return exe
    try:
        import imageio_ffmpeg
    except ImportError:
        raise RuntimeError("ffmpeg not found: pip install imageio-ffmpeg, or install ffmpeg on PATH") from None
    return imageio_ffmpeg.get_ffmpeg_exe()


def duration_seconds(video):
    # `ffmpeg -i` with no output prints the container info, including "Duration: hh:mm:ss.xx", and exits 1.
    out = subprocess.run([ffmpeg_exe(), "-hide_banner", "-i", str(video)], capture_output=True, text=True)
    match = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", out.stderr)
    if not match:
        raise RuntimeError(f"Couldn't read the length of {Path(video).name}; is it a valid video?")
    h, m, sec = match.groups()
    return int(h) * 3600 + int(m) * 60 + float(sec)


def extract_audio(video, out_dir):
    """16 kHz mono WAV, the format Whisper expects."""
    wav = Path(out_dir) / "audio.wav"
    subprocess.run(
        [ffmpeg_exe(), "-y", "-v", "error", "-i", str(video), "-vn", "-ac", "1", "-ar", "16000", str(wav)],
        check=True,
    )
    return wav


def extract_audio_chunks(video, out_dir, chunk_s=1200):
    """Compressed mono MP3 pieces for transcription APIs (OpenAI and Groq cap uploads at 25 MB;
    20 minutes at 32 kbps is about 5 MB). Returns [(offset_seconds, path), ...]."""
    chunk_dir = Path(out_dir) / "audio_chunks"
    chunk_dir.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [ffmpeg_exe(), "-y", "-v", "error", "-i", str(video), "-vn", "-ac", "1", "-ar", "16000",
         "-c:a", "libmp3lame", "-b:a", "32k", "-f", "segment", "-segment_time", str(chunk_s),
         "-reset_timestamps", "1", str(chunk_dir / "chunk_%03d.mp3")],
        check=True,
    )
    chunks, offset = [], 0.0
    for path in sorted(chunk_dir.glob("chunk_*.mp3")):
        chunks.append((offset, path))
        offset += duration_seconds(path)
    return chunks


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
            [ffmpeg_exe(), "-y", "-v", "error", "-ss", f"{t:.2f}", "-i", str(video),
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

"""Recording -> Layer 1 gates + Layer 2 scores -> tier."""

import tempfile

from scoring import claude_scoring, media, transcribe
from scoring.tier import assign_tier, load_rubric


def score_recording(video_path, context, client, transcript_text=None,
                    whisper_model="small", frame_every_s=30, on_step=None):
    """on_step(message, fraction) is called as each stage starts (fraction 0-1)."""
    step = on_step or (lambda msg, frac: None)
    rubric = load_rubric()

    with tempfile.TemporaryDirectory() as work:
        if transcript_text:
            step("Reading uploaded transcript", 0.05)
            segments = transcribe.parse_transcript_file(transcript_text)
            confidence = 1.0  # unknown; don't penalise audio clarity
        else:
            step("Extracting audio", 0.05)
            wav = media.extract_audio(video_path, work)
            step("Transcribing (this is the slow part)", 0.1)
            segments, confidence = transcribe.transcribe(wav, model_size=whisper_model)
        if not segments:
            raise claude_scoring.ScoringError("No speech found in the recording")

        step("Sampling video frames", 0.45)
        frames = media.sample_frames(video_path, work, every_s=frame_every_s)

        step("Checking background, camera and lighting", 0.5)
        frame_results = claude_scoring.check_frames(
            client, frames,
            on_progress=lambda done, total: step(f"Checked {done}/{total} frames", 0.5 + 0.2 * done / total),
        )

    gates, metrics = claude_scoring.gates_from_frames(frame_results, confidence)

    step("Scoring teaching quality", 0.75)
    teaching = claude_scoring.score_teaching(client, rubric, segments, context)

    scores = {k: v["score"] for k, v in teaching["scores"].items()}
    homework = teaching["homework_set"]["value"]
    result = assign_tier(gates, scores, homework, rubric)
    step("Done", 1.0)

    return {
        "context": context,
        "tier": result.tier,
        "score": result.score,
        "weights": {d["id"]: d["weight"] for d in rubric["dimensions"]},
        "reasons": result.reasons,
        "gates": gates,
        "gate_metrics": metrics,
        "frames": frame_results,
        "homework_set": teaching["homework_set"],
        "dimensions": teaching["scores"],
        "strengths": teaching["strengths"],
        "improvements": teaching["improvements"],
        "feedback": teaching["feedback"],
        "transcript": segments,
    }

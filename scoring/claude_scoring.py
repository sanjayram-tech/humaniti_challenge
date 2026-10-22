"""Claude calls: Layer 1 frame checks (vision) and Layer 2 teaching scores (transcript)."""

import base64
import json

import anthropic

from scoring.media import fmt_ts

MODEL = "claude-opus-5-5"
FRAMES_PER_REQUEST = 10


class ScoringError(RuntimeError):
    pass


def _ask_json(client, content, schema, effort, system=None):
    """One structured-output request; returns the parsed JSON object."""
    kwargs = {"system": system} if system else {}
    response = client.beta.messages.create(
        model=MODEL,
        max_tokens=16000,
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
        output_config={"effort": effort, "format": {"type": "json_schema", "schema": schema}},
        messages=[{"role": "user", "content": content}],
        **kwargs,
    )
    if response.stop_reason == "refusal":
        raise ScoringError(f"Claude declined the request ({response.stop_details})")
    if response.stop_reason == "max_tokens":
        raise ScoringError("Claude's answer was cut off (max_tokens); try a shorter recording")
    text = next(b.text for b in response.content if b.type == "text")
    return json.loads(text)


# ---------------------------------------------------------------------------
# Layer 1: frame checks
# ---------------------------------------------------------------------------

FRAME_SCHEMA = {
    "type": "object",
    "properties": {
        "frames": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "index": {"type": "integer"},
                    "chessboard_background": {"type": "boolean"},
                    "face_visible": {"type": "boolean"},
                    "lighting": {"type": "string", "enum": ["good", "dim", "dark", "no_face"]},
                    "glitch": {"type": "boolean"},
                },
                "required": ["index", "chessboard_background", "face_visible", "lighting", "glitch"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["frames"],
    "additionalProperties": False,
}

FRAME_PROMPT = """These are frames from a recorded online chess class for kids. For each frame, report:
- chessboard_background: the tutor's own video uses an 8x8 chessboard as their virtual or physical background
- face_visible: the tutor's face is clearly visible (false if the camera is off, the face is cut off or hidden)
- lighting: "good", "dim" or "dark" for the tutor's face; "no_face" if the face isn't visible
- glitch: the background or video is visibly broken (virtual-background artefacts, freezing, heavy blur)
Frames showing only a shared screen or chessboard diagram with no tutor video count as face_visible false.
Answer for every frame, using the index shown above it."""


def check_frames(client, frames, on_progress=None):
    """frames: [(t, path)]. Returns per-frame dicts with a 't' key added."""
    results = []
    for start in range(0, len(frames), FRAMES_PER_REQUEST):
        batch = frames[start:start + FRAMES_PER_REQUEST]
        content = []
        for i, (t, path) in enumerate(batch):
            data = base64.standard_b64encode(path.read_bytes()).decode("utf-8")
            content.append({"type": "text", "text": f"Frame {i} (at {fmt_ts(t)}):"})
            content.append({"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": data}})
        content.append({"type": "text", "text": FRAME_PROMPT})
        answer = _ask_json(client, content, FRAME_SCHEMA, effort="low")
        by_index = {f["index"]: f for f in answer["frames"]}
        for i, (t, _) in enumerate(batch):
            if i in by_index:
                results.append({**by_index[i], "t": t})
        if on_progress:
            on_progress(min(start + FRAMES_PER_REQUEST, len(frames)), len(frames))
    return results


def _ratio_gate(ratio):
    return "pass" if ratio >= 0.9 else "partial" if ratio >= 0.5 else "fail"


def gates_from_frames(frame_results, transcript_confidence):
    """Turn per-frame checks into Layer 1 gate results (thresholds from rubric.yaml)."""
    n = len(frame_results) or 1
    background = sum(f["chessboard_background"] for f in frame_results) / n
    face = sum(f["face_visible"] for f in frame_results) / n

    lit = [f["lighting"] for f in frame_results if f["face_visible"]]
    good = lit.count("good") / len(lit) if lit else 0
    dark = lit.count("dark") / len(lit) if lit else 1
    lighting = "pass" if good >= 0.8 else "fail" if dark >= 0.5 else "partial"

    glitch = sum(f["glitch"] for f in frame_results) / n
    video_clarity = "fail" if glitch > 0.3 else "partial" if glitch > 0.1 else "pass"
    # Whisper confidence: clear speech is usually > 0.6; below 0.4 is hard to follow.
    audio_clarity = "fail" if transcript_confidence < 0.4 else "partial" if transcript_confidence < 0.55 else "pass"
    av_clarity = max(video_clarity, audio_clarity, key=["pass", "partial", "fail"].index)

    gates = {
        "background": _ratio_gate(background),
        "camera_face": _ratio_gate(face),
        "lighting": lighting,
        "av_clarity": av_clarity,
    }
    metrics = {
        "background_visible": round(background, 2),
        "face_visible": round(face, 2),
        "good_lighting": round(good, 2),
        "glitch_frames": round(glitch, 2),
        "transcript_confidence": round(transcript_confidence, 2),
        "frames_checked": len(frame_results),
    }
    return gates, metrics


# ---------------------------------------------------------------------------
# Layer 2: teaching quality
# ---------------------------------------------------------------------------

def teaching_schema(rubric):
    dim_schema = {
        "type": "object",
        "properties": {
            "score": {"type": "integer", "enum": [1, 2, 3, 4, 5]},
            "insufficient_evidence": {"type": "boolean"},
            "evidence": {"type": "array", "items": {"type": "string"}},
            "reason": {"type": "string"},
        },
        "required": ["score", "insufficient_evidence", "evidence", "reason"],
        "additionalProperties": False,
    }
    dim_ids = [d["id"] for d in rubric["dimensions"]]
    return {
        "type": "object",
        "properties": {
            "homework_set": {
                "type": "object",
                "properties": {"value": {"type": "boolean"}, "evidence": {"type": "string"}},
                "required": ["value", "evidence"],
                "additionalProperties": False,
            },
            "scores": {
                "type": "object",
                "properties": {d: dim_schema for d in dim_ids},
                "required": dim_ids,
                "additionalProperties": False,
            },
            "strengths": {"type": "array", "items": {"type": "string"}},
            "improvements": {"type": "array", "items": {"type": "string"}},
            "feedback": {"type": "string"},
        },
        "required": ["homework_set", "scores", "strengths", "improvements", "feedback"],
        "additionalProperties": False,
    }


def rubric_text(rubric):
    parts = []
    for d in rubric["dimensions"]:
        anchors = "\n".join(f"  {k}: {v}" for k, v in sorted(d["anchors"].items(), reverse=True))
        indicators = "\n".join(f"  - {i}" for i in d["indicators"])
        parts.append(f"### {d['id']} ({d['name']})\nAnchors (2 and 4 sit between):\n{anchors}\nMeasure:\n{indicators}")
    return "\n\n".join(parts)


SYSTEM = """You assess the teaching quality of recorded online chess classes for children, using a fixed rubric.
Score each dimension independently against its anchors only. Ground every score in the transcript:
quote short excerpts with their [hh:mm:ss] timestamps, and give counts where the rubric's Measure lines ask for them.
If the transcript doesn't contain enough to judge a dimension, set insufficient_evidence to true, pick 3, and say why.
Do not assign an overall tier; that is computed from your scores."""


def score_teaching(client, rubric, segments, context):
    transcript = "\n".join(f"[{fmt_ts(s['start'])}] {s['text']}" for s in segments)
    students = context.get("students") or "not provided"
    prompt = f"""<rubric>
{rubric_text(rubric)}
</rubric>

<class_context>
Class level: {context.get('level') or 'not provided'}
Students enrolled: {students}
Notes from the uploader: {context.get('notes') or 'none'}
</class_context>

<transcript>
The transcript is automatic speech-to-text without speaker labels. Infer who is speaking from content:
the tutor leads, explains and asks; children's replies are usually short answers, moves or names.
Transcription errors are likely on chess notation and children's names.

{transcript}
</transcript>

Also report whether homework was set (with a quote), list the main strengths and improvements, and write
`feedback` in the reviewers' house style: one line of short comma-separated phrases, strengths first, then
"should ..." / "need ..." items. Example: "good rapport building, consider everyone in the class, individually
asking questions, given HWs, need more energetic communication"."""
    return _ask_json(client, prompt, teaching_schema(rubric), effort="high", system=SYSTEM)


def make_client(api_key=None):
    return anthropic.Anthropic(api_key=api_key) if api_key else anthropic.Anthropic()

"""Score page: upload a class recording, get a tier, scores and feedback."""

import json
import os
import tempfile
from pathlib import Path

import streamlit as st

from scoring.llm import CUSTOM, PROVIDERS, ScoringError, detect_provider, make_client, provider_from_env
from scoring.media import fmt_ts
from scoring.pipeline import score_recording
from scoring.transcribe import API_PROVIDERS
from scoring.tier import assign_tier, load_rubric

TIER_COLOURS = {
    "Excellent": "green", "Good": "blue", "Average": "orange",
    "Weak": "red", "Quality issue": "violet",
}
GATE_ICONS = {"pass": "✅", "partial": "⚠️", "fail": "❌"}

st.title("♟️ Chess class scorer")
st.caption("Upload a class recording to score it against the 3-layer rubric (rubric/RUBRIC.md).")

rubric = load_rubric()
dim_names = {d["id"]: d["name"] for d in rubric["dimensions"]}
current_weights = {d["id"]: d["weight"] for d in rubric["dimensions"]}
gate_names = {g["id"]: g["name"] for g in rubric["gates"]}

with st.sidebar:
    st.header("LLM")
    api_key = st.text_input(
        "API key", type="password",
        help="Anthropic, OpenAI, Gemini, Groq, OpenRouter and xAI keys are recognised automatically. "
             "Any other key needs the base URL of an OpenAI-compatible API. "
             "Leave empty to use a key from the environment (e.g. OPENAI_API_KEY).",
    ).strip()
    provider = (detect_provider(api_key) or CUSTOM) if api_key else provider_from_env(
        [n for n in PROVIDERS if n != CUSTOM])
    base_url = None
    if provider == CUSTOM:
        base_url = st.text_input(
            "Base URL", placeholder="https://api.mistral.ai/v1",
            help="OpenAI-compatible endpoint, e.g. https://api.deepseek.com or http://localhost:11434/v1 (Ollama).",
        ).strip() or None
    elif provider:
        st.caption(f"Detected **{provider}**" + ("" if api_key else " (key from environment)"))
    model = st.text_input(
        "Model", value=PROVIDERS[provider].model if provider else "", key=f"model_{provider}",
        help="Any model the provider offers. It must accept images for the frame checks.",
    ).strip()
    frame_every_s = st.slider("Check a video frame every (seconds)", 10, 120, 30, 10)

    st.header("Transcription")
    t_mode = st.radio("Run with", ["Local model", "API"], index=1, horizontal=True,
                      help="Local runs faster-whisper on this machine; API sends the audio to OpenAI, Groq or Gemini.")
    if t_mode == "Local model":
        transcription = {"model_size": st.selectbox(
            "Whisper model", ["tiny", "base", "small", "medium", "large-v3"], index=2,
            help="Larger is more accurate but slower. 'small' is a good balance on CPU.",
        )}
    else:
        t_key = st.text_input(
            "Transcription API key", type="password",
            help="OpenAI or Groq key (Whisper), or a Gemini key (Gemini listens to the audio). "
                 "Any other key needs the base URL of an OpenAI-compatible Whisper API. "
                 "Leave empty to reuse the LLM key when it's an OpenAI, Groq or Gemini key.",
        ).strip()
        if not t_key and provider in API_PROVIDERS:
            t_key = api_key or os.environ.get(API_PROVIDERS[provider]["env_var"], "")
        if not t_key and (env := provider_from_env(list(API_PROVIDERS))):
            t_key = os.environ[API_PROVIDERS[env]["env_var"]]
        t_provider = detect_provider(t_key) if t_key else None
        t_preset = API_PROVIDERS.get(t_provider)
        t_base_url = None
        if t_preset:
            st.caption(f"Using **{t_provider}**")
            t_base_url = t_preset["base_url"]
        elif t_key:
            t_base_url = st.text_input("Transcription base URL", placeholder="https://your-endpoint/v1").strip() or None
        t_model = st.text_input(
            "Transcription model", value=t_preset["model"] if t_preset else "whisper-1",
            key=f"t_model_{t_provider}",
            help="Whisper APIs: needs timestamped output (verbose_json), e.g. whisper-1. "
                 "Gemini: any model that accepts audio.",
        ).strip()
        transcription = {"api_key": t_key, "model": t_model, "base_url": t_base_url,
                         "provider": t_provider if t_preset else None}

with st.form("upload"):
    video = st.file_uploader("Class recording", type=["mp4", "mov", "mkv", "webm", "avi", "m4v"])
    transcript_file = st.file_uploader(
        "Transcript (optional, .srt / .vtt / .txt): skips automatic transcription",
        type=["srt", "vtt", "txt"],
    )
    submitted = st.form_submit_button("Score class", type="primary")

if submitted:
    if not video:
        st.error("Upload a recording first.")
        st.stop()
    if not provider:
        st.error("Add an LLM API key in the sidebar.")
        st.stop()
    if not transcript_file and "api_key" in transcription and not transcription["api_key"]:
        st.error("Add a transcription API key, or switch transcription to the local model.")
        st.stop()
    try:
        client = make_client(provider, api_key or None, model, base_url)
    except ScoringError as e:
        st.error(str(e))
        st.stop()

    context = {"file": video.name}
    transcript_text = transcript_file.getvalue().decode("utf-8", errors="replace") if transcript_file else None

    progress = st.progress(0.0, text="Starting")
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / video.name
        path.write_bytes(video.getbuffer())
        try:
            st.session_state.result = score_recording(
                path, context, client,
                transcript_text=transcript_text,
                transcription=transcription,
                frame_every_s=frame_every_s,
                on_step=lambda msg, frac: progress.progress(frac, text=msg),
            )
        except ScoringError as e:
            progress.empty()
            st.error(str(e))
            st.stop()
        except Exception as e:  # surface ffmpeg / API failures in the UI
            progress.empty()
            st.exception(e)
            st.stop()
    progress.empty()

result = st.session_state.get("result")
if result:
    ctx = result["context"]
    weights = result.get("weights", current_weights)
    if weights != current_weights:
        st.warning("The rubric weights have changed since this class was scored.")
        if st.button("Recalculate tier with current weights"):
            scores = {k: v["score"] for k, v in result["dimensions"].items()}
            new = assign_tier(result["gates"], scores, result["homework_set"]["value"], rubric)
            result.update(tier=new.tier, score=new.score, reasons=new.reasons, weights=current_weights)
            st.rerun()

    title = ctx["file"]
    st.divider()
    st.subheader(title, anchor=False)

    c1, c2 = st.columns([1, 2])
    colour = TIER_COLOURS[result["tier"]]
    c1.header(f":{colour}[{result['tier']}]", anchor=False)
    c1.metric("Teaching score (Layer 2)", f"{result['score']} / 5")
    with c2:
        st.markdown("**Feedback**")
        st.info(result["feedback"])
        st.markdown("**How the tier was decided**")
        for r in result["reasons"]:
            st.markdown(f"- {r}")

    st.markdown("#### Layer 1: must-haves")
    m = result["gate_metrics"]
    gate_detail = {
        "background": f"chessboard background in {m['background_visible']:.0%} of frames",
        "camera_face": f"face visible in {m['face_visible']:.0%} of frames",
        "lighting": f"well lit in {m['good_lighting']:.0%} of frames with a face",
        "av_clarity": f"glitches in {m['glitch_frames']:.0%} of frames, transcript confidence {m['transcript_confidence']:.2f}",
    }
    cols = st.columns(len(result["gates"]))
    for col, (gid, outcome) in zip(cols, result["gates"].items()):
        col.markdown(f"**{GATE_ICONS[outcome]} {gate_names[gid]}**  \n{outcome} — {gate_detail[gid]}")
    st.caption(f"{m['frames_checked']} frames checked.")

    st.markdown("#### Layer 2: teaching quality")
    hw = result["homework_set"]
    st.markdown(f"**Homework set:** {'Yes' if hw['value'] else 'No'} — {hw['evidence']}")
    for did, d in result["dimensions"].items():
        flag = " · ⚠️ insufficient evidence" if d["insufficient_evidence"] else ""
        with st.expander(f"{dim_names[did]} — **{d['score']}/5** (weight {weights[did]}){flag}"):
            st.write(d["reason"])
            for e in d["evidence"]:
                st.markdown(f"- {e}")

    s1, s2 = st.columns(2)
    s1.markdown("**Strengths**\n" + "\n".join(f"- {s}" for s in result["strengths"]))
    s2.markdown("**Improvements**\n" + "\n".join(f"- {s}" for s in result["improvements"]))

    with st.expander("Transcript"):
        st.text("\n".join(f"[{fmt_ts(s['start'])}] {s['text']}" for s in result["transcript"]))

    st.download_button(
        "Download result (JSON)",
        json.dumps(result, indent=2, default=str),
        file_name=f"{Path(ctx['file']).stem}_score.json",
        mime="application/json",
    )

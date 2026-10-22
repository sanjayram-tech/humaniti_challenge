"""Score page: upload a class recording, get a tier, scores and feedback."""

import json
import os
import tempfile
from pathlib import Path

import streamlit as st

from scoring.claude_scoring import ScoringError, make_client
from scoring.media import fmt_ts
from scoring.pipeline import score_recording
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
    st.header("Run options")
    api_key = st.text_input(
        "Anthropic API key", type="password",
        help="Leave empty to use ANTHROPIC_API_KEY from the environment.",
    )
    whisper_model = st.selectbox(
        "Transcription model", ["tiny", "base", "small", "medium", "large-v3"], index=2,
        help="Larger is more accurate but slower. 'small' is a good balance on CPU.",
    )
    frame_every_s = st.slider("Check a video frame every (seconds)", 10, 120, 30, 10)

with st.form("upload"):
    video = st.file_uploader("Class recording", type=["mp4", "mov", "mkv", "webm", "avi", "m4v"])
    col1, col2, col3 = st.columns(3)
    batch = col1.text_input("Batch", placeholder="B491")
    tutor = col2.text_input("Tutor", placeholder="Tutor name")
    class_date = col3.date_input("Class date", value=None)
    col4, col5 = st.columns(2)
    level = col4.selectbox("Class level", ["", "Beginner", "Intermediate", "Advanced"])
    students = col5.text_input("Students enrolled (optional)", placeholder="Arjun, Meera, Kabir")
    notes = st.text_area("Notes for the scorer (optional)", height=68)
    transcript_file = st.file_uploader(
        "Transcript (optional, .srt / .vtt / .txt): skips automatic transcription",
        type=["srt", "vtt", "txt"],
    )
    submitted = st.form_submit_button("Score class", type="primary")

if submitted:
    if not video:
        st.error("Upload a recording first.")
        st.stop()
    if not (api_key or os.environ.get("ANTHROPIC_API_KEY")):
        st.error("Add an Anthropic API key in the sidebar, or set ANTHROPIC_API_KEY.")
        st.stop()

    context = {
        "batch": batch, "tutor": tutor,
        "date": class_date.isoformat() if class_date else "",
        "level": level, "students": students, "notes": notes,
        "file": video.name,
    }
    transcript_text = transcript_file.getvalue().decode("utf-8", errors="replace") if transcript_file else None

    progress = st.progress(0.0, text="Starting")
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / video.name
        path.write_bytes(video.getbuffer())
        try:
            st.session_state.result = score_recording(
                path, context, make_client(api_key or None),
                transcript_text=transcript_text,
                whisper_model=whisper_model,
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

    title = " · ".join(x for x in [ctx.get("batch"), ctx.get("tutor"), ctx.get("date")] if x) or ctx["file"]
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
        file_name=f"{(ctx.get('batch') or 'class')}_{ctx.get('date') or 'score'}.json",
        mime="application/json",
    )

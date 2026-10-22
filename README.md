# humaniti_challenge

Rating recorded online chess classes for kids as Excellent / Good / Average / Weak /
Quality issue, using a 3-layer rubric that AI and human reviewers share.

## Scoring app

Upload a recording and get a tier, per-dimension scores with timestamped evidence,
and feedback in the reviewers' style.

```sh
pip install -r requirements.txt        # also needs ffmpeg on PATH
export ANTHROPIC_API_KEY=sk-ant-...    # or paste it in the app's sidebar
streamlit run app.py
```

What happens to an upload:
1. **Audio → transcript** locally with faster-whisper (the model downloads on first use).
   You can upload an `.srt` / `.vtt` / `.txt` transcript instead to skip this step.
2. **Frames → Layer 1 gates.** One frame every 30 s goes to Claude to check the
   chessboard background, face visibility, lighting and glitches.
3. **Transcript → Layer 2 scores.** Claude scores the 8 dimensions against the rubric anchors.
4. **Tier** from [`scoring/tier.py`](scoring/tier.py); the AI never picks the tier itself.

Results can be downloaded as JSON.

Limitations: the transcript has no speaker labels (Claude infers tutor vs. students),
and energy/tone is judged from words only, not from the voice.

## Rubric

- [`rubric/RUBRIC.md`](rubric/RUBRIC.md): the scoring guide (start here)
- [`rubric/rubric.yaml`](rubric/rubric.yaml): machine-readable rubric
- [`rubric/calibration/reviewed_classes.yaml`](rubric/calibration/reviewed_classes.yaml): the 10 classes reviewers have already rated

## Tests

```sh
python3 -m unittest -v
```

---
title: Chess Class Scorer
emoji: ♟️
colorFrom: indigo
colorTo: gray
sdk: docker
app_port: 8501
pinned: false
---

# humaniti_challenge: Chess Class Scorer

Upload a recorded chess class and get a quality tier, teaching scores and feedback.

## Setup

Needs Python 3.10+.

```sh
git clone git@github.com:sanjayram-tech/humaniti_challenge.git
cd humaniti_challenge
python -m venv .venv
```

Windows:

```powershell
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python -m streamlit run app.py
```

macOS / Linux:

```sh
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m streamlit run app.py
```

Open http://localhost:8501.

## Get a Gemini API key (free)

1. Go to https://aistudio.google.com/apikey and sign in with a Google account.
2. Accept the terms if asked, then click **Create API key**.
3. Pick an existing Google Cloud project or let it create one, and confirm.
4. Copy the key (it starts with `AIza`). Keep it private; anyone with it can use your quota.

The free tier has rate and daily limits; check them on the same page if requests start failing.

## Use

1. Paste your Gemini API key in the sidebar. It is used for everything: transcription,
   frame checks and scoring.
2. Upload the class video (optionally a `.srt` / `.vtt` / `.txt` transcript) and click **Score class**.

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

## Use

1. Paste your Gemini API key in the sidebar (free at https://aistudio.google.com/apikey).
   It is used for everything: transcription, frame checks and scoring.
2. Upload the class video (optionally a `.srt` / `.vtt` / `.txt` transcript) and click **Score class**.

## Deploy (Hugging Face Spaces)

1. Create a Space at https://huggingface.co/new-space, choosing **Docker** → **Blank**.
2. Push this code to it (use an HF access token with write access as the password):

   ```sh
   git remote add space https://huggingface.co/spaces/<your-username>/<space-name>
   git push space HEAD:main
   ```

The Space builds the `Dockerfile` and serves the app. Users paste their own API keys in the sidebar.
Don't add API keys as Space secrets on a public Space: anyone could then use them.

## Tests

```sh
python -m unittest
```

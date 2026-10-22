# Image for Hugging Face Spaces (Docker SDK) or any Docker host.
FROM python:3.11-slim

# Spaces run the container as user 1000; give it a home for the Whisper model cache.
RUN useradd -m -u 1000 user
USER user
ENV HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH \
    PYTHONUNBUFFERED=1
WORKDIR /home/user/app

COPY --chown=user requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

COPY --chown=user . .

EXPOSE 8501
# XSRF/CORS checks are off because Spaces serve the app inside an iframe, where they block uploads.
CMD ["streamlit", "run", "app.py", \
     "--server.address=0.0.0.0", "--server.port=8501", "--server.headless=true", \
     "--server.enableXsrfProtection=false", "--server.enableCORS=false"]

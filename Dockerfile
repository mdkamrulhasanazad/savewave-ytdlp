FROM python:3.11-slim

# ffmpeg is required to merge separate video+audio streams (needed for
# 1080p and above, since YouTube doesn't serve those pre-muxed) and to
# extract MP3 audio.
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app.py .

ENV PORT=5000
EXPOSE 5000

CMD gunicorn app:app --bind 0.0.0.0:$PORT --timeout 300 --workers 1

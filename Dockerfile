FROM python:3.12-slim

WORKDIR /app

# Install ffmpeg + dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Install Python deps
COPY requirements.txt .
RUN pip install --no-cache-dir gunicorn -r requirements.txt

# App code
COPY . .

# Hugging Face Spaces uses port 7860
ENV PORT=7860
ENV FLASK_SECRET_KEY="hf-default-secret-change-me"

EXPOSE 7860

CMD ["gunicorn", "app:app", "--bind", "0.0.0.0:7860", "--workers", "2", "--timeout", "120", "--access-logfile", "-"]

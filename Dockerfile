FROM python:3.12-slim

WORKDIR /app

# Install system deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libpq-dev && \
    rm -rf /var/lib/apt/lists/*

# Install Python deps
COPY autosre/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY autosre/ ./autosre/

# Set working directory to autosre for proper imports
WORKDIR /app/autosre

# Cloud Run sets PORT env var, all secrets come via --set-env-vars
ENV PORT=8080
ENV PYTHONUNBUFFERED=1

EXPOSE 8080

CMD ["uvicorn", "gateway.main:app", "--host", "0.0.0.0", "--port", "8080", "--workers", "1"]

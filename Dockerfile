FROM python:3.11-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app/src \
    HOST=0.0.0.0

# tzdata so a TZ set at deploy time (e.g. TZ=Australia/Sydney) actually resolves —
# python:3.11-slim ships without it, so date.today() would otherwise stay UTC.
RUN apt-get update && apt-get install -y --no-install-recommends tzdata \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ ./src/
COPY scripts/ ./scripts/

EXPOSE 8000
# Default entrypoint = the web server. The batch is the same image run with a
# different command: `docker compose run --rm app python scripts/run_digest.py`.
CMD ["python", "scripts/serve_web.py"]

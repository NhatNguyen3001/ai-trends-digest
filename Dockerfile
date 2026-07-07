FROM python:3.11-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app/src \
    HOST=0.0.0.0

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ ./src/
COPY scripts/ ./scripts/

EXPOSE 8000
# Default entrypoint = the web server. The batch is the same image run with a
# different command: `docker compose run --rm app python scripts/run_digest.py`.
CMD ["python", "scripts/serve_web.py"]

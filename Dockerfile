# Build stage
FROM python:3.12-slim AS builder

WORKDIR /app
COPY pyproject.toml .
COPY bot/__init__.py ./bot/
RUN pip install --user --no-cache-dir .

# Runtime stage
FROM python:3.12-slim

WORKDIR /app

# Copy dependencies from builder
COPY --from=builder /root/.local /root/.local
ENV PATH=/root/.local/bin:$PATH

# Copy application code only
COPY bot/ ./bot/
COPY bot.py .

# Logs directory (mount as volume)
VOLUME /app/logs

HEALTHCHECK --interval=60s --timeout=10s --start-period=30s --retries=3 \
    CMD python -c "import time;from pathlib import Path;t=float(Path('/app/logs/.heartbeat').read_text());exit(0 if time.time()-t<120 else 1)"

CMD ["python", "bot.py"]

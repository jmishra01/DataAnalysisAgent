FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Install the application before copying frequently changed demo/runtime files.
COPY pyproject.toml README.md ./
COPY src ./src
RUN python -m pip install .

COPY cli.py ./cli.py
COPY data ./data

RUN useradd --create-home --uid 10001 appuser \
    && mkdir -p /app/.agent_state /app/logs \
    && chown -R appuser:appuser /app

USER appuser

ENTRYPOINT ["python", "cli.py"]
CMD ["--csv", "/app/data/retail.csv", "--question", "Maximum units sold by product category", "--session", "docker-demo"]

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DATA_DIR=/data/pesc

WORKDIR /app

COPY pyproject.toml README.md ./
COPY portal ./portal
COPY src ./src
COPY templates ./templates

RUN pip install --no-cache-dir . \
    && mkdir -p /app/static /data/pesc

EXPOSE 8000

CMD ["uvicorn", "portal.main:app", "--host", "0.0.0.0", "--port", "8000"]

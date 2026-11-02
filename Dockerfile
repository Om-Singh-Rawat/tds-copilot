# Public demo image: standard-library Python, no dependencies.
#   docker build -t tds-copilot .
#   docker run -p 8080:8080 tds-copilot                                  # cached LLM answers only
#   docker run -p 8080:8080 -e TDS_LIVE_LLM=1 -e OPENROUTER_API_KEY=... tds-copilot
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HOST=0.0.0.0 \
    PORT=8080 \
    TDS_PUBLIC=1 \
    TDS_LIVE_LLM=0

WORKDIR /app
COPY tds ./tds
COPY data ./data
COPY .cache ./.cache

RUN useradd --create-home appuser && chown -R appuser /app
USER appuser

EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=3s CMD python -c "import urllib.request,os;urllib.request.urlopen(f'http://127.0.0.1:{os.environ[\"PORT\"]}/healthz')"
CMD ["python", "-m", "tds", "serve"]

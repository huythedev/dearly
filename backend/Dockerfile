FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DEARLY_DB=/data/dearly.sqlite3 \
    DEARLY_PORT=8002

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && useradd --uid 10001 --create-home dearly \
    && mkdir /data \
    && chown dearly:dearly /data

COPY server.py run.py localization.py translations.vi.json realtime.py web_support.py ./
USER dearly

VOLUME ["/data"]
EXPOSE 8002

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:' + os.environ['DEARLY_PORT'] + '/health', timeout=3).close()"

CMD ["python", "run.py", "serve", "--host", "0.0.0.0"]

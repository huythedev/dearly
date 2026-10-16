FROM node:24-alpine AS web
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY web/ ./
RUN npm run build

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DEARLY_DB=/data/dearly.sqlite3 \
    DEARLY_WEB_DIST=/app/web-dist

WORKDIR /app

COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && useradd --uid 10001 --create-home dearly \
    && mkdir /data \
    && chown dearly:dearly /data

COPY backend/server.py backend/run.py backend/localization.py backend/translations.vi.json backend/realtime.py backend/web_support.py ./
COPY --from=web /web/dist /app/web-dist
USER dearly

VOLUME ["/data"]
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3).close()"

CMD ["python", "run.py", "serve", "--host", "0.0.0.0", "--port", "8000"]

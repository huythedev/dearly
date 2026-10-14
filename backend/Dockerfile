FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && useradd --create-home dearly && mkdir /data && chown dearly /data
COPY server.py run.py ./
USER dearly
ENV DEARLY_DB=/data/dearly.sqlite3
VOLUME ["/data"]
EXPOSE 8000
CMD ["python", "run.py", "serve", "--host", "0.0.0.0", "--port", "8000"]

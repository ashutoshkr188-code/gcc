FROM python:3.12-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code, static web assets, research data and database
COPY gcc_atlas gcc_atlas
COPY web web
COPY research research
COPY data/inbox data/inbox
COPY data/gcc_atlas.sqlite data/gcc_atlas.sqlite

# SQLite lives on a mounted volume so it survives restarts and redeploys
ENV GCC_ATLAS_DB=/data/gcc_atlas.sqlite
VOLUME ["/data"]
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health')" || exit 1

# If mounted /data is empty, initialize it with the bundled database, apply migrations, and serve
CMD ["sh", "-c", "mkdir -p /data && if [ ! -f /data/gcc_atlas.sqlite ] && [ -f /app/data/gcc_atlas.sqlite ]; then cp /app/data/gcc_atlas.sqlite /data/gcc_atlas.sqlite; fi && python -m gcc_atlas.cli init && python -m gcc_atlas.cli serve --host 0.0.0.0 --port 8000"]

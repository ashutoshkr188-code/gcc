FROM python:3.13-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY gcc_atlas gcc_atlas
COPY web web
COPY research research
COPY data/inbox data/inbox
# SQLite lives on a mounted volume so it survives restarts and redeploys.
ENV GCC_ATLAS_DB=/data/gcc_atlas.sqlite
VOLUME ["/data"]
EXPOSE 8000
# Migrations and seeding are idempotent, so running them on every start is safe.
CMD ["sh", "-c", "python -m gcc_atlas.cli seed && python -m gcc_atlas.cli serve --host 0.0.0.0 --port 8000"]

FROM node:24-alpine AS frontend-build
WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM nginx:1.29-alpine AS web
COPY ops/nginx.conf /etc/nginx/templates/default.conf.template
COPY --from=frontend-build /app/frontend/dist /usr/share/nginx/html
HEALTHCHECK --interval=15s --timeout=3s --retries=5 CMD wget -q -O - http://127.0.0.1/healthz || exit 1

FROM python:3.12-slim-bookworm AS backend
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends \
    fonts-dejavu-core \
    libffi8 \
    libharfbuzz-subset0 \
    libpango-1.0-0 \
    libpangoft2-1.0-0 \
    shared-mime-info \
    && rm -rf /var/lib/apt/lists/*
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY alembic.ini pyproject.toml README.md ./
COPY migrations ./migrations
COPY engine ./engine
COPY server ./server
RUN useradd --create-home --uid 10001 unimate && mkdir -p /data && chown -R unimate:unimate /data /app
USER unimate
ENV UNIMATE_STORAGE_ROOT=/data
HEALTHCHECK --interval=15s --timeout=3s --retries=5 CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health/live', timeout=2)" || exit 1
CMD ["uvicorn", "server.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--proxy-headers", "--forwarded-allow-ips=*", "--no-access-log"]

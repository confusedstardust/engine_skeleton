# syntax=docker/dockerfile:1.7

FROM node:20-alpine AS engine-builder
WORKDIR /build

COPY package.json package-lock.json tsconfig.json tsconfig.node.json vite.config.ts index.html ./
COPY public ./public
COPY scripts ./scripts
COPY src ./src

RUN npm ci --legacy-peer-deps
RUN npm run build


FROM python:3.11-slim AS runner

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    WEBGAL_BACKEND_ROOT=/app \
    WEBGAL_JOBS_DIR=/data/jobs

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 libgomp1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install -r requirements.txt

COPY webgal_backend ./webgal_backend
COPY asset_scripts ./asset_scripts
COPY public ./public
COPY .env.example ./.env.example
COPY --from=engine-builder /build/dist ./dist

RUN useradd --create-home --shell /bin/bash appuser \
    && mkdir -p /data/jobs \
    && chown -R appuser:appuser /app /data/jobs

USER appuser

EXPOSE 8010

CMD ["uvicorn", "webgal_backend.app:app", "--host", "0.0.0.0", "--port", "8010"]


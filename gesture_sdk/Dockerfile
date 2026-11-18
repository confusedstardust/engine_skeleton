# The build stage downloads the pinned MediaPipe model at build time.
FROM node:22-alpine AS assets
WORKDIR /build
COPY gesture_sdk/package.json ./
RUN npm install --no-audit --no-fund
COPY gesture_sdk/src ./src
COPY gesture_sdk/build.mjs ./
RUN npm run build

FROM python:3.11-slim AS runner
WORKDIR /app
RUN pip install --no-cache-dir fastapi==0.115.12 uvicorn==0.34.2
COPY gesture_sdk/server.py gesture_sdk/review.py /app/gesture_sdk/
COPY nar_agent/app/template_catalog.py /app/gesture_sdk/template_catalog.py
COPY nar_agent/templates/gesture-cards /app/gesture_sdk/templates/gesture-cards
COPY --from=assets /build/dist/gesture-sdk/v1 /app/gesture_sdk/dist/gesture-sdk/v1
RUN useradd --uid 1000 --create-home arplayer
USER 1000:1000
EXPOSE 8040
CMD ["uvicorn","gesture_sdk.server:app","--host","0.0.0.0","--port","8040"]

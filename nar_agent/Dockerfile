FROM python:3.13-slim
COPY --from=ghcr.io/astral-sh/uv:0.11.7 /uv /usr/local/bin/uv
WORKDIR /srv/nar-agent
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev
COPY app ./app
COPY agents ./agents
COPY skills ./skills
RUN useradd --uid 10001 --create-home naragent && mkdir -p /data/artifacts && chown 10001:10001 /data/artifacts
USER naragent
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1 NAR_AGENT_ARTIFACT_DIR=/data/artifacts
EXPOSE 8020
CMD [".venv/bin/uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8020"]

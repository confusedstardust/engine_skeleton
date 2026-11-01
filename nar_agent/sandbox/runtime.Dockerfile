FROM node:22-bookworm-slim
RUN apt-get update && apt-get install -y --no-install-recommends chromium fonts-noto-cjk ca-certificates \
    && rm -rf /var/lib/apt/lists/*
COPY skills/anatomy /opt/anatomy
COPY sandbox/run.mjs sandbox/browser-check.mjs /opt/runner/
ENV CHROME_PATH=/usr/bin/chromium
ENV HOME=/tmp XDG_CONFIG_HOME=/tmp/.config XDG_CACHE_HOME=/tmp/.cache
WORKDIR /work
# Trusted supervisor drops generated Node/Chromium processes to UID 65532.
USER 0:0
ENTRYPOINT ["node", "/opt/runner/run.mjs"]

# syntax=docker/dockerfile:1.7

FROM node:20-alpine AS deps
WORKDIR /build/forge_frontend_next

COPY forge_frontend_next/package.json forge_frontend_next/package-lock.json ./
RUN npm ci


FROM node:20-alpine AS builder
WORKDIR /build/forge_frontend_next

ARG FORGE_BACKEND_URL=http://backend:8010
ENV FORGE_BACKEND_URL=${FORGE_BACKEND_URL}

COPY --from=deps /build/forge_frontend_next/node_modules ./node_modules
COPY forge_frontend_next ./

RUN npm run build


FROM node:20-alpine AS runner
WORKDIR /app

ENV NODE_ENV=production \
    HOSTNAME=0.0.0.0 \
    PORT=3001 \
    FORGE_BACKEND_URL=http://backend:8010

COPY --from=builder /build/forge_frontend_next/.next/standalone ./
COPY --from=builder /build/forge_frontend_next/.next/static ./.next/static

EXPOSE 3001

CMD ["node", "server.js"]

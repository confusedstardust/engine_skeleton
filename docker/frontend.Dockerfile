# syntax=docker/dockerfile:1.7

FROM node:20-alpine AS deps
WORKDIR /app

COPY forge_frontend_next/package.json forge_frontend_next/package-lock.json ./
RUN npm ci


FROM node:20-alpine AS builder
WORKDIR /app

ARG FORGE_BACKEND_URL=http://backend:8010
ENV FORGE_BACKEND_URL=${FORGE_BACKEND_URL}

COPY --from=deps /app/node_modules ./node_modules
COPY forge_frontend_next ./

RUN npm run build


FROM node:20-alpine AS runner
WORKDIR /app

ENV NODE_ENV=production \
    HOSTNAME=0.0.0.0 \
    PORT=3001 \
    FORGE_BACKEND_URL=http://backend:8010

COPY --from=builder /app/package.json ./package.json
COPY --from=builder /app/package-lock.json ./package-lock.json
COPY --from=builder /app/node_modules ./node_modules
COPY --from=builder /app/.next ./.next
COPY --from=builder /app/next.config.mjs ./next.config.mjs
COPY --from=builder /app/tsconfig.json ./tsconfig.json
COPY --from=builder /app/app ./app

EXPOSE 3001

CMD ["npm", "run", "start"]

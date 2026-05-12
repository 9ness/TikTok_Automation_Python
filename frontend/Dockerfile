# syntax=docker/dockerfile:1.6
#
# Imagen Next.js (output standalone). Multi-stage:
#   1. deps    — npm install
#   2. builder — npm run build (NEXT_PUBLIC_API_URL inyectado vía ARG)
#   3. runner  — solo standalone server + static + public
#
# Build:
#   docker build \
#     --build-arg NEXT_PUBLIC_API_URL=https://api.example.com \
#     --build-arg NEXT_PUBLIC_WS_URL=wss://api.example.com \
#     -t tiktok-web:latest \
#     ./frontend

# ---------------------------------------------------------------------------
# 1. deps
# ---------------------------------------------------------------------------
FROM node:20-alpine AS deps
WORKDIR /app

# alpine necesita libc6-compat para ciertos binarios npm.
RUN apk add --no-cache libc6-compat

COPY package.json package-lock.json* ./
RUN npm ci

# ---------------------------------------------------------------------------
# 2. builder
# ---------------------------------------------------------------------------
FROM node:20-alpine AS builder
WORKDIR /app

# Estos ARG se inlinean en el bundle (cualquier `NEXT_PUBLIC_*` se materializa
# en build-time, no runtime). Pásalos via --build-arg en docker-compose.
ARG NEXT_PUBLIC_API_URL=http://localhost:8000
ARG NEXT_PUBLIC_WS_URL=ws://localhost:8000
ARG NEXT_PUBLIC_API_KEY=
ENV NEXT_PUBLIC_API_URL=${NEXT_PUBLIC_API_URL} \
    NEXT_PUBLIC_WS_URL=${NEXT_PUBLIC_WS_URL} \
    NEXT_PUBLIC_API_KEY=${NEXT_PUBLIC_API_KEY} \
    NEXT_TELEMETRY_DISABLED=1

COPY --from=deps /app/node_modules ./node_modules
COPY . .

# Next.js 14 con App Router no crea `public/` por defecto. Lo garantizamos
# aquí para que el COPY del stage runner siempre tenga algo que copiar
# (aunque esté vacío).
RUN mkdir -p public

RUN npm run build

# ---------------------------------------------------------------------------
# 3. runner — output standalone
# ---------------------------------------------------------------------------
FROM node:20-alpine AS runner
WORKDIR /app

ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=3000 \
    HOSTNAME=0.0.0.0

# Usuario no-root (mismo patrón que la doc oficial Next.js).
RUN addgroup --system --gid 1001 nodejs && \
    adduser --system --uid 1001 nextjs

# `output: "standalone"` en next.config.mjs deja un server.js minimal +
# node_modules estrictamente necesarios en .next/standalone.
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static
COPY --from=builder --chown=nextjs:nodejs /app/public ./public

USER nextjs

EXPOSE 3000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD wget --quiet --tries=1 --spider http://127.0.0.1:3000 || exit 1

CMD ["node", "server.js"]

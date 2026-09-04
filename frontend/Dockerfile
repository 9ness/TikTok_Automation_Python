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
# Por defecto VACÍAS: vacío significa "llama al mismo origen desde el que se
# abrió la página", que es lo que hace que la app funcione por cualquier
# puerta (el dominio, el nombre de reserva, el que venga mañana).
#
# Y hay un motivo para que el defecto sea vacío y no una URL: docker ignora un
# `--build-arg X=` vacío y se queda con el DEFECTO del Dockerfile. Con un
# defecto que fuera una URL, dejar la variable vacía en el `.env` no servía de
# nada — el bundle se construía con la URL de siempre y la app solo funcionaba
# por la puerta con la que se compiló. Costó una mañana de "Failed to fetch".
ARG NEXT_PUBLIC_API_URL=
ARG NEXT_PUBLIC_WS_URL=
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

# syntax=docker/dockerfile:1.7
# Multi-stage Next.js build → small standalone runtime image.

FROM node:20-slim AS deps
WORKDIR /app
COPY package.json ./
# No committed lockfile → use install (not ci). Reproducibility is bounded by
# the pinned versions in package.json.
RUN npm install --no-audit --no-fund

FROM node:20-slim AS builder
WORKDIR /app
ENV NEXT_TELEMETRY_DISABLED=1
COPY --from=deps /app/node_modules ./node_modules
COPY . .
RUN npm run build

FROM node:20-slim AS runner
WORKDIR /app
ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=3000 \
    TZ=Europe/Zurich
RUN apt-get update && apt-get install -y --no-install-recommends curl tzdata && rm -rf /var/lib/apt/lists/*
# Standalone output bundles the server + traced node_modules.
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static
COPY --from=builder /app/public ./public
EXPOSE 3000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD curl -fsS http://localhost:3000/ || exit 1
CMD ["node", "server.js"]

# syntax=docker/dockerfile:1.7
# Multi-stage Next.js build → small standalone runtime image.

FROM node:20-slim AS deps
WORKDIR /app
COPY package.json package-lock.json ./
# Use the lockfile so Docker resolves the SAME sub-dep tree we tested
# locally. Without it the typescript/Next sub-deps drifted and webpack
# stopped honouring tsconfig path aliases.
RUN npm ci --no-audit --no-fund --include=dev

FROM node:20-slim AS builder
WORKDIR /app
ENV NEXT_TELEMETRY_DISABLED=1
COPY --from=deps /app/node_modules ./node_modules
COPY . .
# Diagnostic — make sure tsconfig + src actually arrived (cheap; helps next
# time the build breaks for an obscure reason).
RUN test -f tsconfig.json && test -f src/lib/api.ts || (echo "BUILD CONTEXT MISSING FILES" && ls -la && exit 1)
RUN npm run build

FROM node:20-slim AS runner
WORKDIR /app
# HOSTNAME=0.0.0.0 is load-bearing. Next.js standalone server.js binds
# `process.env.HOSTNAME || "0.0.0.0"`, and Docker sets HOSTNAME to the
# container id. The server therefore resolved that name and bound ONLY the
# container's eth0 address (verified in production: /proc/net/tcp showed
# 172.16.1.4:3000 and nothing on loopback). Proxied traffic worked, so the
# fault was invisible, but the HEALTHCHECK below probes localhost and failed
# every 30s for the entire life of the container -- a failing streak of 24310
# on a container that was serving normally. Binding all interfaces makes the
# probe meaningful again.
ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    HOSTNAME=0.0.0.0 \
    PORT=3000 \
    TZ=Europe/Zurich
RUN apt-get update && apt-get install -y --no-install-recommends curl tzdata && rm -rf /var/lib/apt/lists/*
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static
COPY --from=builder /app/public ./public
EXPOSE 3000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD curl -fsS http://localhost:3000/ || exit 1
CMD ["node", "server.js"]

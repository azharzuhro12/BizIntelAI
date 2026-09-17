# BizIntel AI - image frontend Next.js (context build = ./frontend).
# Multi-stage: deps -> build (standalone) -> runner non-root.
# NEXT_PUBLIC_API_URL di-inline saat BUILD lewat build-arg (nilai publik,
# bukan rahasia); tidak ada kredensial GLM/LLM di sisi client.

FROM node:22-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci

FROM node:22-alpine AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .
# URL API dilihat browser host -> default port mapping compose (localhost:8020)
ARG NEXT_PUBLIC_API_URL=http://localhost:8020
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL
RUN npm run build

FROM node:22-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production
# Docker men-set HOSTNAME=<id container>; server.js standalone Next memakainya
# untuk bind lalu gagal resolve DNS (EAI_AGAIN). Pin ke 0.0.0.0 agar listen
# di semua interface seperti perilaku standalone standar.
ENV HOSTNAME=0.0.0.0
RUN addgroup -S nodejs && adduser -S nextjs -G nodejs
COPY --from=builder /app/public ./public
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static
USER nextjs
EXPOSE 3000
CMD ["node", "server.js"]

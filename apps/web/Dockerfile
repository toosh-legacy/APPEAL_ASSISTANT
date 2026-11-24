# Next.js web app (standalone output).
#   docker build -f apps/web/Dockerfile --build-arg NEXT_PUBLIC_API_URL=https://api.example.com -t appeal-web .
# NEXT_PUBLIC_API_URL is baked in at build time (Next inlines NEXT_PUBLIC_* into the browser bundle).
FROM node:22-slim AS deps
WORKDIR /web
COPY apps/web/package.json apps/web/package-lock.json ./
RUN --mount=type=cache,target=/root/.npm npm ci

FROM node:22-slim AS build
WORKDIR /web
ARG NEXT_PUBLIC_API_URL=http://127.0.0.1:8000
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL NEXT_OUTPUT=standalone NEXT_TELEMETRY_DISABLED=1
COPY --from=deps /web/node_modules ./node_modules
COPY apps/web/ ./
RUN npm run build

FROM node:22-slim AS run
WORKDIR /web
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1 PORT=3100 HOSTNAME=0.0.0.0
COPY --from=build --chown=node /web/.next/standalone ./
COPY --from=build --chown=node /web/.next/static ./.next/static
COPY --from=build --chown=node /web/public ./public
USER node
EXPOSE 3100
CMD ["node", "server.js"]

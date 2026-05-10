# syntax=docker/dockerfile:1.9
# claude-tracker frontend — Vite 8 + React 19 on Node 22

# ---- Stage 1: install npm deps (cached) --------------------------------------
FROM node:22.12.0-bookworm-slim AS deps

WORKDIR /app
COPY package.json ./
# We deliberately do NOT copy package-lock.json here. Vite 8 + Rolldown ship
# platform-specific optional native bindings (e.g. @rolldown/binding-linux-*),
# and npm 10/11 has a long-standing bug (#4828) where those bindings get
# skipped if the lockfile was generated on a different OS/arch. Letting npm
# resolve fresh inside the container guarantees the linux-arm64/x64 binding
# is picked up. The top-level pins in package.json are still exact.
RUN --mount=type=cache,target=/root/.npm \
    npm install --include=optional --no-audit --no-fund


# ---- Stage 2: dev server (default target) ------------------------------------
FROM node:22.12.0-bookworm-slim AS dev

ENV NODE_ENV=development \
    HOST=0.0.0.0

WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .

EXPOSE 5173
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0", "--port", "5173"]


# ---- Stage 3: production build artefact --------------------------------------
FROM node:22.12.0-bookworm-slim AS build

WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .
RUN npm run build


# ---- Stage 4: nginx-served prod static ---------------------------------------
FROM nginx:1.27.3-alpine AS prod

# Replace default config so / serves index.html and SPA routes work
RUN rm /etc/nginx/conf.d/default.conf
COPY docker/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]

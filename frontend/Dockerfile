# --- development: hot-reload Vite dev server (docker-compose.yml's default
# `frontend` service target — day-to-day dev workflow is unchanged) ---
FROM node:20-slim AS development

WORKDIR /app

COPY package.json ./
RUN npm install

COPY . .

EXPOSE 5173

CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]


# --- build: compiles the static bundle, shared by the production stage only ---
FROM node:20-slim AS build

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY . .
RUN npm run build


# --- production: static bundle served by nginx, no Node runtime in the
# final image, no source volume-mounted — this is what `frontend-prod`
# (docker-compose.yml, profile "prod") builds ---
FROM nginx:1.27-alpine AS production

COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

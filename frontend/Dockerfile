# Dev image for the Vite + React frontend.
#
# Compose bind-mounts ./frontend over /app for HMR; an anonymous volume on
# /app/node_modules preserves the deps that `npm ci` installed in the image
# (otherwise the host bind mount would mask them).
FROM node:22-alpine

WORKDIR /app

# --ignore-scripts skips the root-level `prepare` lifecycle which runs
# `git config core.hooksPath` — there is no git repo inside the container.
COPY package.json package-lock.json ./
RUN npm ci --ignore-scripts

COPY . .

EXPOSE 5173

# `--` forwards `--host` to vite so it binds 0.0.0.0 inside the container.
CMD ["npm", "run", "dev", "--", "--host"]

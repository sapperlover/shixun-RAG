# syntax=docker/dockerfile:1
# 构建上下文为仓库根目录（见 docker-compose.yml）。

# 开发镜像：依赖装在镜像里；源码由 docker-compose.dev.yml 挂载
FROM node:22-alpine AS dev
ARG NPM_REGISTRY=https://registry.npmjs.org
RUN mkdir -p /repo/frontend && chown -R node:node /repo
USER node
WORKDIR /repo/frontend
COPY --chown=node:node frontend/package.json frontend/package-lock.json ./
RUN npm ci --registry=${NPM_REGISTRY}
EXPOSE 5173
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]

# 构建
FROM node:22-alpine AS build
ARG NPM_REGISTRY=https://registry.npmjs.org
WORKDIR /repo/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --registry=${NPM_REGISTRY}
COPY contracts /repo/contracts
COPY frontend ./
RUN npm run build

# 交付镜像
FROM nginx:1.27-alpine AS prod
COPY frontend/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /repo/frontend/dist /usr/share/nginx/html
EXPOSE 80

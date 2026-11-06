# syntax=docker/dockerfile:1
# 构建上下文为仓库根目录（见 docker-compose.yml）。
FROM python:3.11-slim AS base
ARG APP_UID=1000
ARG PIP_INDEX_URL=https://pypi.org/simple
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_INDEX_URL=${PIP_INDEX_URL} \
    PYTHONPATH=/app/backend \
    REPO_ROOT=/app
WORKDIR /app
RUN useradd -m -u ${APP_UID} app \
 && mkdir -p /data/app /data/faiss /data/model_cache /data/uploads \
 && chown -R app:app /data /app
COPY backend/requirements.lock backend/requirements.lock
RUN pip install -r backend/requirements.lock

# 开发镜像：只装依赖，源码由 docker-compose.dev.yml 挂载到 /app
FROM base AS dev
COPY backend/requirements-dev.lock backend/requirements-dev.lock
RUN pip install -r backend/requirements-dev.lock
USER app
WORKDIR /app/backend
EXPOSE 8000 5678
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload", "--reload-dir", "/app/backend/app", "--reload-dir", "/app/config"]

# 交付镜像
FROM base AS prod
ARG GIT_COMMIT=unknown
ENV GIT_COMMIT=${GIT_COMMIT}
COPY --chown=app:app config config
COPY --chown=app:app contracts contracts
COPY --chown=app:app backend backend
USER app
WORKDIR /app/backend
EXPOSE 8000
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --root-path \"${ROOT_PATH:-}\""]

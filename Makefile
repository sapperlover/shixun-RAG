# 常用命令入口。所有命令都在容器里执行，宿主机只需要 Docker + make。
SHELL := /bin/bash
-include .env

export APP_UID := $(shell id -u)
export GIT_COMMIT := $(shell git rev-parse --short HEAD 2>/dev/null || echo unknown)

BASE    := docker compose -f docker-compose.yml $(if $(GPU),-f docker-compose.gpu.yml)
DEV     := docker compose -f docker-compose.yml -f docker-compose.dev.yml $(if $(GPU),-f docker-compose.gpu.yml)
RUN_API := $(DEV) run --rm --no-deps api
RUN_WEB := $(DEV) run --rm --no-deps web
LLM_MODEL ?= qwen2.5:1.5b

.PHONY: help env up down dev init health test lint fmt typecheck check shell logs ps lock eval schema baseline clean-volumes

help: ## 列出命令
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk -F':.*?## ' '{printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

env: ## 首次使用：生成 .env
	@test -f .env || (cp .env.example .env && echo "已生成 .env，请修改 NEO4J_PASSWORD")

up: env ## 交付基线启动（GPU=1 启用 GPU 叠加）
	$(BASE) up -d --build

down: ## 停止所有容器（保留数据卷）
	$(DEV) down

dev: env ## 开发模式：热重载 api(:8000) + Vite(:5173)
	$(DEV) up --build

init: ## 首次启动后：建 Neo4j 约束、迁移 SQLite、拉取模型
	$(BASE) exec api python -m scripts.init_sqlite
	$(BASE) exec api python -m scripts.init_neo4j
	$(BASE) exec ollama ollama pull $(LLM_MODEL)

health: ## 查看 /health/ready
	@curl -s http://localhost:$(or $(WEB_PORT),8080)/api/health/ready | python3 -m json.tool

test: ## 后端单元/接口/契约测试（不依赖外部服务）
	$(RUN_API) pytest

lint: ## 后端 ruff + 前端 eslint/prettier
	$(RUN_API) sh -c "ruff check . && ruff format --check ."
	$(RUN_WEB) sh -c "npm run lint && npm run format:check"

fmt: ## 自动格式化
	$(RUN_API) sh -c "ruff check --fix . && ruff format ."
	$(RUN_WEB) sh -c "npm run lint -- --fix && npm run format"

typecheck: ## 前端类型检查
	$(RUN_WEB) npm run typecheck

check: lint typecheck test ## 提交前全量检查

shell: ## 进入 api 开发容器
	$(DEV) exec api bash

logs: ## 跟踪日志
	$(DEV) logs -f --tail=100

ps:
	$(DEV) ps

schema: ## 由 Pydantic 模型重新导出 contracts/qa_ask.schema.json（改契约后必须执行）
	$(RUN_API) python -m scripts.export_schema

lock: ## 由 requirements*.in 重新生成锁文件
	docker run --rm -u $(APP_UID):$(APP_UID) -e HOME=/tmp -e PIP_INDEX_URL=$(or $(PIP_INDEX_URL),https://pypi.org/simple) \
	  -e UV_INDEX_URL=$(or $(PIP_INDEX_URL),https://pypi.org/simple) \
	  -v $(CURDIR)/backend:/w -w /w python:3.11-slim sh -c "\
	  pip install -q --user uv && \
	  /tmp/.local/bin/uv pip compile -q --no-header --no-annotate -o requirements.lock requirements.in && \
	  /tmp/.local/bin/uv pip compile -q --no-header --no-annotate -o requirements-dev.lock requirements-dev.in"

eval: ## 用冻结题集运行评测（与线上同一条 pipeline）
	$(DEV) exec api python -m scripts.run_eval

baseline: ## 记录镜像 digest、模型、锁文件校验值到 docs/BASELINE.md
	@bash scripts/record_baseline.sh > docs/BASELINE.md && echo "已写入 docs/BASELINE.md"

clean-volumes: ## 危险：删除所有数据卷（图谱、SQLite、模型）
	@read -p "将删除全部数据卷，输入 yes 确认: " a && [ "$$a" = yes ] && $(DEV) down -v

#!/usr/bin/env bash
# 输出部署基线（V1.2 附录 D.2）：镜像 digest、模型、锁文件校验值、硬件。用法：make baseline
set -euo pipefail
set -a; [ -f .env ] && . ./.env; set +a
echo "# 部署基线记录"
echo
echo "生成时间：$(date '+%F %T')；git：$(git rev-parse --short HEAD 2>/dev/null || echo 未提交)"
echo
echo "## 镜像"
for img in "neo4j:${NEO4J_IMAGE_TAG:-5.26.0-community}" "ollama/ollama:${OLLAMA_IMAGE_TAG:-0.5.7}" python:3.11-slim node:22-alpine nginx:1.27-alpine; do
  d=$(docker image inspect --format '{{index .RepoDigests 0}}' "$img" 2>/dev/null || echo "未拉取")
  echo "- \`$img\` → \`$d\`"
done
echo
echo "## 模型"
docker compose exec -T ollama ollama list 2>/dev/null | sed 's/^/    /' || echo "- Ollama 未运行"
echo
echo "## 锁文件 sha256"
for f in backend/requirements.lock backend/requirements-dev.lock frontend/package-lock.json; do
  echo "- \`$f\` $(sha256sum "$f" | cut -c1-16)"
done
echo
echo "## 硬件"
echo "- CPU：$(nproc) 核；内存：$(free -h | awk '/Mem:/{print $2}')"
echo "- GPU：$(nvidia-smi --query-gpu=name,memory.total --format=csv,noheader 2>/dev/null || echo 无)"

# 部署基线记录

生成时间：2026-11-06 11:23:50；git：f95f0b1

## 镜像
- `neo4j:5.26.0-community` → `neo4j@sha256:5a015e53de1895e7eee1574ae0325cf8c4b89587222778108c594bdd45a474b5`
- `ollama/ollama:0.5.7` → `ollama/ollama@sha256:7e672211886f8bd4448a98ed577e26c816b9e8b052112860564afaa2c105800e`
- `python:3.11-slim` → `python@sha256:65bd3d9f1d7fa268dd1909973ba7eb4bdf41f6dcf2cfbe76ba9528b170f3fd79`
- `node:22-alpine` → `node@sha256:0e1754758c2df4cfa3e68d59e2e1b7374bb7fd9ea6328eaaacf15cc934af8202`
- `nginx:1.27-alpine` → `nginx@sha256:65645c7bb6a0661892a8b03b89d0743208a18dd2f3f17a54ef4b76fb8e2f2a10`

## 模型
    NAME            ID              SIZE      MODIFIED       
    qwen2.5:1.5b    65ec06548149    986 MB    39 seconds ago    

## 锁文件 sha256
- `backend/requirements.lock` 4332828728feb198
- `backend/requirements-dev.lock` 654e6e0882fc28f7
- `frontend/package-lock.json` 2a83f8e43c5b93ff

## 硬件
- CPU：16 核；内存：31.1 GB
- GPU：NVIDIA GeForce RTX 4050 Laptop GPU, 6141 MiB

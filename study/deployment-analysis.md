# DeepTutor 部署方案分析

## 概述

DeepTutor 支持多种部署方式，包括 **Docker 容器化部署** 和 **手动安装部署**，适用于本地开发和云端生产环境。

---

## 1. Docker 部署架构

### 1.1 多阶段构建

Dockerfile 采用 **4 阶段构建**，优化镜像大小和构建缓存:

```
Stage 1: frontend-builder     Stage 2: python-base
┌─────────────────────┐      ┌─────────────────────┐
│  node:22-slim       │      │  python:3.11-slim   │
│  ├─ npm ci          │      │  ├─ apt-get deps    │
│  ├─ COPY web/       │      │  ├─ pip install     │
│  └─ npm run build   │      │  └─ requirements.txt│
└─────────────────────┘      └─────────────────────┘
           │                            │
           └────────────┬───────────────┘
                        ▼
              Stage 3: production
              ┌─────────────────────┐
              │  python:3.11-slim   │
              │  ├─ COPY from S1    │
              │  │   └─ .next/      │
              │  ├─ COPY from S2    │
              │  │   └─ site-pkg/   │
              │  ├─ COPY src/       │
              │  ├─ supervisor      │
              │  └─ entrypoint.sh   │
              └─────────────────────┘
                        │
                        ▼
              Stage 4: development
              ┌─────────────────────┐
              │  FROM production    │
              │  ├─ dev tools       │
              │  └─ --reload mode   │
              └─────────────────────┘
```

### 1.2 构建命令

```bash
# 生产构建 (默认)
docker compose build

# 开发构建
docker compose -f docker-compose.yml -f docker-compose.dev.yml build

# 清除缓存重建
docker compose build --no-cache
```

---

## 2. Docker Compose 配置

### 2.1 服务定义

```yaml
services:
  deeptutor:
    build:
      context: .
      dockerfile: Dockerfile
      target: production
      args:
        - BACKEND_PORT=${BACKEND_PORT:-8001}
    
    container_name: deeptutor
    restart: unless-stopped
    
    ports:
      - "${BACKEND_PORT:-8001}:${BACKEND_PORT:-8001}"
      - "${FRONTEND_PORT:-3782}:${FRONTEND_PORT:-3782}"
    
    env_file:
      - .env
    
    volumes:
      - ./config:/app/config:ro      # 只读配置
      - ./data/user:/app/data/user   # 读写用户数据
      - ./data/knowledge_bases:/app/data/knowledge_bases
    
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:${BACKEND_PORT:-8001}/"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 60s
```

### 2.2 网络配置

```yaml
networks:
  deeptutor-network:
    driver: bridge
```

---

## 3. 环境变量配置

### 3.1 必需变量

| 变量 | 说明 | 示例 |
|------|------|------|
| `LLM_BINDING` | LLM 提供商 | `openai` |
| `LLM_MODEL` | 模型名称 | `gpt-4o` |
| `LLM_API_KEY` | API 密钥 | `sk-xxx` |
| `LLM_HOST` | API 端点 | `https://api.openai.com/v1` |
| `EMBEDDING_BINDING` | 嵌入提供商 | `openai` |
| `EMBEDDING_MODEL` | 嵌入模型 | `text-embedding-3-small` |
| `EMBEDDING_API_KEY` | 嵌入 API 密钥 | `sk-xxx` |
| `EMBEDDING_HOST` | 嵌入 API 端点 | `https://api.openai.com/v1` |
| `EMBEDDING_DIMENSION` | 向量维度 | `3072` |

### 3.2 可选变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `BACKEND_PORT` | `8001` | 后端端口 |
| `FRONTEND_PORT` | `3782` | 前端端口 |
| `LLM_API_VERSION` | - | Azure API 版本 |
| `TTS_MODEL` | - | TTS 模型 |
| `TTS_API_KEY` | - | TTS API 密钥 |
| `TTS_URL` | - | TTS API 端点 |
| `TTS_VOICE` | `alloy` | TTS 声音 |
| `SEARCH_PROVIDER` | `perplexity` | 搜索提供商 |
| `SEARCH_API_KEY` | - | 搜索 API 密钥 |
| `DISABLE_SSL_VERIFY` | `false` | 禁用 SSL 验证 |

### 3.3 云部署变量

| 变量 | 说明 |
|------|------|
| `NEXT_PUBLIC_API_BASE_EXTERNAL` | 外部 API URL (云部署必需) |
| `NEXT_PUBLIC_API_BASE` | 自定义 API URL |

---

## 4. 进程管理

### 4.1 Supervisor 配置

```ini
[supervisord]
nodaemon=true
logfile=/dev/null
pidfile=/var/run/supervisord.pid

[program:backend]
command=/bin/bash /app/start-backend.sh
directory=/app
autostart=true
autorestart=true
stdout_logfile=/dev/fd/1
stderr_logfile=/dev/fd/2

[program:frontend]
command=/bin/bash /app/start-frontend.sh
directory=/app/web
autostart=true
autorestart=true
startsecs=5
stdout_logfile=/dev/fd/1
stderr_logfile=/dev/fd/2
```

### 4.2 启动脚本

**后端启动 (`start-backend.sh`):**
```bash
#!/bin/bash
BACKEND_PORT=${BACKEND_PORT:-8001}
echo "[Backend] 🚀 Starting FastAPI on port ${BACKEND_PORT}..."
exec python -m uvicorn src.api.main:app --host 0.0.0.0 --port ${BACKEND_PORT}
```

**前端启动 (`start-frontend.sh`):**
```bash
#!/bin/bash
BACKEND_PORT=${BACKEND_PORT:-8001}
FRONTEND_PORT=${FRONTEND_PORT:-3782}

# API URL 优先级: EXTERNAL > CUSTOM > DEFAULT
if [ -n "$NEXT_PUBLIC_API_BASE_EXTERNAL" ]; then
    API_BASE="$NEXT_PUBLIC_API_BASE_EXTERNAL"
elif [ -n "$NEXT_PUBLIC_API_BASE" ]; then
    API_BASE="$NEXT_PUBLIC_API_BASE"
else
    API_BASE="http://localhost:${BACKEND_PORT}"
fi

# 替换构建时的占位符
find /app/web/.next -type f \( -name "*.js" -o -name "*.json" \) \
    -exec sed -i "s|__NEXT_PUBLIC_API_BASE_PLACEHOLDER__|${API_BASE}|g" {} \;

# 启动 Next.js
cd /app/web && exec node node_modules/next/dist/bin/next start -H 0.0.0.0 -p ${FRONTEND_PORT}
```

---

## 5. 部署模式

### 5.1 本地开发部署

```bash
# 方式 1: Docker Compose
docker compose up

# 方式 2: 手动启动
python scripts/start_web.py
```

### 5.2 生产部署

```bash
# 使用预构建镜像
docker run -d --name deeptutor \
  -p 8001:8001 -p 3782:3782 \
  --env-file .env \
  -v $(pwd)/data:/app/data \
  -v $(pwd)/config:/app/config:ro \
  ghcr.io/hkuds/deeptutor:latest
```

### 5.3 云部署

```bash
# 设置外部 API URL
docker run -d --name deeptutor \
  -p 8001:8001 -p 3782:3782 \
  -e NEXT_PUBLIC_API_BASE_EXTERNAL=https://your-server.com:8001 \
  --env-file .env \
  -v $(pwd)/data:/app/data \
  ghcr.io/hkuds/deeptutor:latest
```

### 5.4 自定义端口

```bash
docker run -d --name deeptutor \
  -p 9001:9001 -p 3000:3000 \
  -e BACKEND_PORT=9001 \
  -e FRONTEND_PORT=3000 \
  -e NEXT_PUBLIC_API_BASE_EXTERNAL=https://your-server.com:9001 \
  --env-file .env \
  -v $(pwd)/data:/app/data \
  ghcr.io/hkuds/deeptutor:latest
```

---

## 6. 镜像标签

| 标签 | 架构 | 说明 |
|------|------|------|
| `:latest` | AMD64 + ARM64 | 最新稳定版 (自动检测架构) |
| `:v0.x.x` | AMD64 + ARM64 | 指定版本 (自动检测架构) |
| `:v0.x.x-amd64` | AMD64 | 显式 AMD64 镜像 |
| `:v0.x.x-arm64` | ARM64 | 显式 ARM64 镜像 |

---

## 7. 数据持久化

### 7.1 Volume 挂载

```yaml
volumes:
  # 配置文件 (只读)
  - ./config:/app/config:ro
  
  # 用户数据 (读写)
  - ./data/user:/app/data/user
  
  # 知识库 (读写)
  - ./data/knowledge_bases:/app/data/knowledge_bases
```

### 7.2 数据目录结构

```
data/
├── knowledge_bases/              # 知识库存储
│   └── {kb_name}/
│       ├── documents/           # 原始文档
│       ├── chunks/              # 分块数据
│       └── vectors/             # 向量索引
└── user/                         # 用户活动数据
    ├── solve/                    # 求解结果
    ├── question/                 # 生成题目
    ├── research/                 # 研究报告
    │   ├── cache/               # 研究缓存
    │   └── reports/             # 最终报告
    ├── guide/                    # 学习会话
    ├── notebook/                 # 笔记本
    ├── co-writer/                # 写作内容
    │   ├── audio/               # TTS 音频
    │   └── tool_calls/          # 工具调用记录
    ├── logs/                     # 系统日志
    └── run_code_workspace/       # 代码执行
```

---

## 8. 健康检查

### 8.1 Docker 健康检查

```yaml
healthcheck:
  test: ["CMD", "curl", "-f", "http://localhost:${BACKEND_PORT:-8001}/"]
  interval: 30s
  timeout: 10s
  retries: 3
  start_period: 60s
```

### 8.2 检查端点

| 端点 | 方法 | 说明 |
|------|------|------|
| `/` | GET | 根路径，返回欢迎消息 |
| `/docs` | GET | Swagger API 文档 |
| `/api/v1/system/health` | GET | 系统健康状态 |

---

## 9. 常用命令

### 9.1 Docker Compose

```bash
# 启动服务
docker compose up -d

# 停止服务
docker compose down

# 查看日志
docker compose logs -f

# 重建并启动
docker compose up --build

# 清除缓存重建
docker compose build --no-cache
```

### 9.2 Docker 单独运行

```bash
# 拉取镜像
docker pull ghcr.io/hkuds/deeptutor:latest

# 运行容器
docker run -d --name deeptutor \
  -p 8001:8001 -p 3782:3782 \
  --env-file .env \
  -v $(pwd)/data:/app/data \
  -v $(pwd)/config:/app/config:ro \
  ghcr.io/hkuds/deeptutor:latest

# 查看日志
docker logs -f deeptutor

# 进入容器
docker exec -it deeptutor /bin/bash

# 停止并删除
docker stop deeptutor && docker rm deeptutor
```

---

## 10. 手动安装部署

### 10.1 环境要求

- Python 3.10+
- Node.js 18+
- pip / npm

### 10.2 安装步骤

```bash
# 1. 克隆仓库
git clone https://github.com/HKUDS/DeepTutor.git
cd DeepTutor

# 2. 创建虚拟环境
conda create -n deeptutor python=3.10
conda activate deeptutor

# 3. 安装依赖
python scripts/install_all.py
# 或: pip install -r requirements.txt && npm install --prefix web

# 4. 配置环境变量
cp .env.example .env
# 编辑 .env 文件

# 5. 启动服务
python scripts/start_web.py
```

### 10.3 分离启动

```bash
# 后端
python src/api/run_server.py
# 或: uvicorn src.api.main:app --host 0.0.0.0 --port 8001 --reload

# 前端
cd web && npm run dev -- -p 3782
```

---

## 11. 故障排除

### 11.1 常见问题

| 问题 | 原因 | 解决方案 |
|------|------|----------|
| API 连接失败 | CORS/网络 | 检查 `NEXT_PUBLIC_API_BASE` |
| LLM 调用失败 | API Key 无效 | 检查 `.env` 配置 |
| 知识库为空 | 未上传文档 | 访问 `/knowledge` 上传 |
| 容器启动慢 | 首次构建 | 等待 ~11 分钟 |
| 端口冲突 | 端口被占用 | 修改 `BACKEND_PORT`/`FRONTEND_PORT` |

### 11.2 日志查看

```bash
# Docker 日志
docker compose logs -f

# 应用日志
cat data/user/logs/ai_tutor_*.log
```

---

## 总结

DeepTutor 部署方案支持:

1. **Docker 一键部署** - 推荐方式，环境隔离
2. **预构建镜像** - 快速启动，无需构建
3. **手动安装** - 适合开发调试
4. **云部署** - 支持外部 API URL 配置

关键配置:
- **环境变量** - `.env` 文件管理敏感信息
- **配置文件** - `config/main.yaml` 管理应用参数
- **数据持久化** - Volume 挂载确保数据不丢失

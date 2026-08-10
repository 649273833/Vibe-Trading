# Vibe-Trading 本地开发指南

本指南涵盖 Vibe-Trading 项目的本地运行、代码拉取与提交的标准流程，方便统一查阅，减少每次开发需要重新探索的时间。

## 项目概览

| 组件 | 技术栈 | 根目录 |
|------|--------|--------|
| 后端 | Python 3.11–3.13, FastAPI, uvicorn, LangChain | `agent/` |
| 前端 | React 19, Vite 6, Tailwind CSS 3, TypeScript | `frontend/` |
| 容器化 | Docker Compose（多阶段构建） | `docker-compose.yml`, `Dockerfile` |

- **默认端口**: 后端 `8899`, 前端 `5899`
- **LLM 配置**: 见 `agent/.env`（已配置 DeepSeek）
- **入口**: CLI `vibe-trading`, MCP `vibe-trading-mcp`

---

## 1. 环境准备

### 1.1 必需依赖

| 工具 | 最低版本 | 安装方式 |
|------|----------|----------|
| Python | ≥3.11, <3.14 | 系统安装 或 pyenv |
| Node.js | ≥22.22.0 | nvm（推荐） |
| Git | 任意较新版本 | 系统自带 |

### 1.2 Python 虚拟环境

```bash
cd /path/to/Vibe-Trading

# 创建虚拟环境
python3 -m venv .venv

# 激活 + 安装项目依赖
source .venv/bin/activate
pip install -e ".[dev]"        # 含 black, ruff, pytest
```

### 1.3 Node.js（通过 nvm）

```bash
# 安装并切换到 Node 22
nvm install 22
nvm use 22
nvm alias default 22

# 安装前端依赖
cd frontend && npm install && cd ..
```

---

## 2. 配置

### 2.1 后端配置 (`agent/.env`)

该项目已通过 `.gitignore` 排除 `agent/.env`。复制模板修改即可：

```bash
# 项目已自带 agent/.env，如不需要改 LLM 可跳过此步
cp agent/.env.example agent/.env    # 仅首次
```

核心配置项（只需填一个 Provider）：

```env
# --- DeepSeek (当前已启用) ---
LANGCHAIN_PROVIDER=deepseek
LANGCHAIN_MODEL_NAME=deepseek-v4-pro
DEEPSEEK_API_KEY=sk-你的key
DEEPSEEK_BASE_URL=https://api.deepseek.com/v1

# --- OpenAI ---
# LANGCHAIN_PROVIDER=openai
# LANGCHAIN_MODEL_NAME=gpt-5.5-instant
# OPENAI_API_KEY=sk-xxx

# --- Ollama 本地 ---
# LANGCHAIN_PROVIDER=ollama
# LANGCHAIN_MODEL_NAME=qwen2.5:32b
# OLLAMA_BASE_URL=http://localhost:11434
```

其他支持 Provider 见文件注释：OpenRouter, Anthropic, Gemini, Groq, DashScope, Zhipu, Moonshot, 等。

### 2.2 前端配置 (`frontend/.env`)

```env
VITE_API_URL=http://127.0.0.1:8899
```

本地开发时后端默认跑在 `8899`，docker-compose 中也一样；如手动跑后端用 `8000`，需改为 `http://127.0.0.1:8000`。

---

## 3. 运行项目

### 方式一：开发脚本（推荐，一键启动前后端）

```bash
cd /path/to/Vibe-Trading

# 启动前后端（后台运行，日志写入 .vibe-dev/logs/）
./scripts/dev up

# 查看状态
./scripts/dev status

# 查看日志
./scripts/dev logs           # 前后端一起看
./scripts/dev logs backend   # 只看后端

# 停止
./scripts/dev stop

# 重启某个服务
./scripts/dev restart backend
./scripts/dev restart frontend

# 在浏览器中打开
./scripts/dev open
```

启动后访问：
- 前端: http://127.0.0.1:5899
- 后端: http://127.0.0.1:8899
- API 文档: http://127.0.0.1:8899/docs

自定义端口（可选）：

```bash
VIBE_BACKEND_PORT=9000 VIBE_FRONTEND_PORT=6000 ./scripts/dev up
```

### 方式二：手动启动（两个终端）

**终端 1 — 后端：**

```bash
source .venv/bin/activate
PYTHONPATH="$PWD/agent" python -c 'import cli; cli.main(["serve","--host","127.0.0.1","--port","8899"])'
```

**终端 2 — 前端：**

```bash
cd frontend
VITE_API_URL=http://127.0.0.1:8899 npm run dev -- --host 127.0.0.1 --port 5899
```

### 方式三：Docker（需要 Docker Engine ≥20.10）

```bash
# 仅后端
docker compose up -d

# 后端 + 前端
docker compose --profile frontend up -d

# 停止
docker compose --profile frontend down
```

Docker 模式下，`agent/.env` 会绑定挂载到容器内，修改后需 `docker compose restart` 生效。

### 方式四：仅交互式 CLI

```bash
source .venv/bin/activate
vibe-trading chat          # 交互式对话
vibe-trading run -p "分析 AAPL 过去一个月走势"   # 单次运行
vibe-trading serve         # 仅启动 API 服务
```

---

## 4. Git 工作流

### 4.1 远程仓库

```bash
# 查看当前 remote
git remote -v

# origin   → 你的 fork（可推送）
# upstream → 上游主仓库（只读，用于同步）
```

### 4.2 拉取上游最新代码

项目已配置 upstream（指向 `HKUDS/Vibe-Trading`）。同步步骤：

```bash
# 1. 切换到 main
git checkout main

# 2. 拉取 upstream 最新代码
git fetch upstream

# 3. 合并到本地 main
git merge upstream/main

# 4. 推送到你的 origin
git push origin main
```

如果本地有未提交的修改，先 `git stash` 暂存，同步完再用 `git stash pop` 恢复。

### 4.3 提交代码流程

```bash
# 1. 从最新的 main 建功能分支
git checkout main
git fetch upstream
git merge upstream/main
git checkout -b feat/你的功能名

# 2. 开发 + 自测（运行下方的 lint 和测试）

# 3. 提交（必须带 -s 做 DCO 签名）
git add <changed-files>
git commit -s -m "feat(xxx): 简要描述改动"

# 4. 推送到自己的 fork
git push origin feat/你的功能名

# 5. 在 GitHub 上创建 PR（从你的分支 → upstream/main）
```

**重要**：社区 PR 的每个 commit 必须带 `Signed-off-by:`（DCO 要求）。用 `git commit -s` 自动添加。

### 4.4 修复未签名的提交

```bash
git rebase --signoff upstream/main
git push --force-with-lease
```

---

## 5. 测试与代码检查

### 5.1 运行测试

```bash
source .venv/bin/activate

# 全部单元测试（不含 e2e）
pytest agent/tests/ --ignore=agent/tests/e2e_backtest -q

# 仅某类测试
pytest agent/tests/factors/test_alpha_purity.py -q
pytest agent/tests/factors/test_lookahead.py -q
```

### 5.2 代码风格

```bash
# 格式化检查
black --check agent/src/your_file.py agent/tests/test_your_file.py

# Lint
ruff check agent/src/your_file.py agent/tests/test_your_file.py

# 自动修复
black agent/src/your_file.py
ruff check --fix agent/src/your_file.py
```

配置在 `pyproject.toml` 的 `[tool.ruff]` 和 `[tool.black]`（行宽 120）。

### 5.3 前端测试

```bash
cd frontend
npm test          # vitest
npm run build     # 确认构建无错误
```

---

## 6. 目录结构速查

```
Vibe-Trading/
├── agent/                      # Python 后端
│   ├── .env                    # 后端配置（LLM、数据源等）
│   ├── .env.example            # 配置模板（包含所有可选 Provider）
│   ├── src/agent/              # 核心 Agent 逻辑
│   │   ├── context.py         # 上下文构建
│   │   ├── grounding.py       # 信息检索
│   │   ├── loop.py            # Agent 主循环
│   │   ├── skills.py          # 技能加载
│   │   └── tools.py           # 工具注册
│   ├── src/factors/            # Alpha 因子库 + 回测引擎
│   ├── backtest/               # 回测模块
│   ├── cli/                    # CLI 入口
│   └── tests/                  # Python 测试
├── frontend/                   # React 前端
│   ├── .env                    # VITE_API_URL 配置
│   ├── src/                    # 前端源码
│   ├── vite.config.ts          # Vite 配置（端口 + API 代理）
│   └── package.json            # 前端脚本 + 依赖
├── scripts/
│   └── dev                     # 开发管理脚本（start/stop/logs/status）
├── docker-compose.yml          # Docker 编排
├── Dockerfile                  # 生产镜像构建
├── pyproject.toml              # Python 项目元数据 + 工具配置
└── .gitignore                  # 已排除 agent/.env 等敏感文件
```

---

## 7. 常见问题

| 问题 | 解决 |
|------|------|
| `permission denied: ./scripts/dev` | `chmod +x scripts/dev` |
| Node 版本过低 (`v18.x` 不满足 `≥22.22.0`) | `nvm install 22 && nvm use 22` |
| 前端报 404 找不到 API | 检查 `frontend/.env` 的 `VITE_API_URL` 是否指向正确的后端地址 |
| `pip install -e ".[dev]"` 失败 | 先确认 Python ≥3.11；macOS 上 `llvmlite` 可能需 `brew install cmake` |
| 后端启动报缺少模块 | 确认 `source .venv/bin/activate` 且执行了 `pip install -e .` |
| Docker 模式下前端不启动 | 加 `--profile frontend`：`docker compose --profile frontend up -d` |
| 端口被占用 | 自定义端口：`VIBE_BACKEND_PORT=9000 VIBE_FRONTEND_PORT=6000 ./scripts/dev up` |
| `frontend/node_modules` 丢失 | `cd frontend && npm install` |

---

## 8. 备忘：常用命令一览

```bash
# ===== 运行 =====
./scripts/dev up              # 一键启动前后端
./scripts/dev stop            # 停止
./scripts/dev logs            # 查看日志
./scripts/dev status          # 查看状态

# ===== Git =====
git fetch upstream && git merge upstream/main     # 同步上游
git checkout -b feat/my-change                    # 建分支
git commit -s -m "feat(xxx): description"         # 带 DCO 签名提交
git push origin feat/my-change                    # 推送

# ===== 测试 / Lint =====
pytest agent/tests/ --ignore=agent/tests/e2e_backtest -q
black --check agent/src/file.py && ruff check agent/src/file.py
cd frontend && npm test && npm run build

# ===== 工具 =====
source .venv/bin/activate     # 激活虚拟环境
vibe-trading chat             # 交互式 CLI
```

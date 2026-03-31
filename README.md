# Policy Center - 政策数据管理平台

政策数据管理平台，用于管理全国31个省级行政区（332个地级市）的多类型政策（社保基数、公积金基数、平均工资、人才政策等）。外部 Agent 通过 REST API 提交数据，经人工审核后发布。

## 在线 Demo

**地址**: https://uhawkrwrpffr.ap-northeast-1.clawcloudrun.com/

| 账号 | 密码 | 权限 |
|------|------|------|
| `admin` | `admin123` | 管理员，可操作所有功能 |

> Demo 数据每天凌晨 3 点（北京时间）自动重置，包含 12 个城市的社保、公积金、社平工资及人才政策样本数据，以及若干待审核记录。重置后管理员账号和 Agent API Key 恢复默认。

**Agent API Key（供 Agent 接入测试）**: 请联系项目作者获取，或登录管理后台 → 系统管理 → API Keys 查看。

**API 文档**: https://uhawkrwrpffr.ap-northeast-1.clawcloudrun.com/docs

---

## 功能特性

- **多类型政策管理**: 社保基数、公积金基数、社会平均工资、人才政策，支持管理员自定义扩展类型
- **审核流程**: Agent 提交 → 校验 → 人工审核 → 发布，支持追溯缴纳标记
- **版本管理**: 完整的版本历史、变更追踪，支持小修和大版本两种编辑模式
- **地区管理**: 内置全国 31 省份及 332 个地级市行政区划数据
- **Agent REST API**: 标准化 REST API，支持外部 Agent 自动化采集和提交政策数据
- **Demo 模式**: 一键开启定时数据重置，适合公开演示

## 快速开始（本地开发）

### 1. 安装依赖

```bash
# 后端依赖
pip install -r requirements.txt

# 前端依赖
cd web && npm install
```

### 2. 配置环境变量

```bash
cp .env.example .env
# 编辑 .env，至少修改 JWT_SECRET_KEY
```

### 3. 启动服务

```bash
# 后端（端口 8000，--reload 热重载）
python run.py

# 前端（新终端，端口 3000，自动代理 /api 到后端）
cd web && npm run dev
```

### 4. 访问

- **前端界面**: http://localhost:3000
- **API 文档**: http://localhost:8000/docs
- **默认登录**: `admin` / `admin123`

---

## Docker 部署

### 使用预构建镜像（推荐）

镜像托管在 GitHub Container Registry，无需本地构建：

```bash
docker pull ghcr.io/fjy046918/policy-center:latest
```

### docker-compose 启动

```bash
# 复制并编辑环境变量
cp .env.example .env

# 启动（首次会自动初始化数据库和地区数据）
docker-compose up -d

# 查看日志
docker-compose logs -f
```

### 环境变量说明

**必填：**

| 变量 | 说明 |
|------|------|
| `DATABASE_URL` | `sqlite+aiosqlite:////app/data/policy_center.db`（注意4个斜杠） |
| `JWT_SECRET_KEY` | 随机字符串，48位以上，生产环境必须修改 |

**Demo 模式（公开展示时开启）：**

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `DEMO_MODE` | `false` | 设为 `true` 启用自动 seed 和定时重置 |
| `DEMO_AGENT_API_KEY` | — | Demo Agent 固定 API Key 明文，重置后保持不变 |
| `DEMO_RESET_CRON` | `0 3 * * *` | 重置时间，cron 格式，Asia/Shanghai 时区 |

**可选：**

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `STORAGE_PATH` | `/app/uploads` | 上传文件路径 |
| `LOG_LEVEL` | `INFO` | 日志级别 |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `480` | Token 有效期（分钟） |

### 持久化挂载

| 容器内路径 | 说明 |
|------------|------|
| `/app/data` | SQLite 数据库，**必须挂载** |
| `/app/uploads` | 上传附件 |
| `/app/logs` | 应用日志（可选） |

---

## CI/CD

项目通过 GitHub Actions 自动构建并推送镜像到 GHCR：

- 推送到 `main` / `master` 分支 → 构建并推送 `:latest`
- 推送 `v*` tag → 同时生成版本号 tag（如 `:1.2.3`）
- 支持手动触发（Actions 页面 → Run workflow）

无需配置额外 Secrets，使用内置 `GITHUB_TOKEN` 即可推送到 GHCR。

---

## 项目结构

```
policy_center/
├── app/                      # 后端代码
│   ├── api/                  # REST API 路由
│   │   ├── auth.py          # 认证登录
│   │   ├── policies.py      # 政策 CRUD
│   │   ├── reviews.py       # 审核中心
│   │   ├── admin.py         # 系统管理
│   │   ├── agent.py         # Agent REST API
│   │   └── dashboard.py     # 数据看板
│   ├── models/              # SQLAlchemy ORM 模型
│   ├── schemas/             # Pydantic 请求/响应模式
│   ├── services/            # 业务逻辑层
│   ├── config.py            # 配置管理（含 Demo 模式）
│   ├── database.py          # 数据库连接与初始化
│   ├── demo_seed.py         # Demo 模式样本数据与重置逻辑
│   └── main.py              # FastAPI 应用入口
├── web/                      # 前端代码（React + TypeScript + Vite）
│   └── src/
│       ├── components/      # 公共组件
│       ├── pages/           # 页面组件
│       ├── services/        # API 服务层（axios）
│       ├── stores/          # Zustand 状态管理
│       └── types/           # TypeScript 类型定义
├── data/
│   └── regions.json         # 行政区划数据（31省 + 332市）
├── tests/                    # pytest 测试
├── .github/workflows/        # GitHub Actions CI/CD
├── docker-entrypoint.sh      # 容器启动脚本（chown 后降权）
├── requirements.txt
├── run.py                    # 后端开发启动脚本
├── Dockerfile
├── docker-compose.yml
└── .env.example
```

---

## 数据初始化

系统首次启动时自动执行：

1. 创建所有数据库表结构
2. 创建默认管理员账户（`admin` / `admin123`）
3. 加载行政区划数据（31 省份 + 332 地级市）
4. 注册内置政策类型（社保、公积金、社平工资、人才政策）

开启 Demo 模式时额外执行：

5. 写入 12 个城市的多类型样本政策数据
6. 写入若干待审核记录
7. 启动 APScheduler 定时任务，按 `DEMO_RESET_CRON` 周期全量重置

---

## Agent API

外部 Agent 通过 REST API 提交政策数据，提交进入人工审核队列，审核通过后发布为 active 状态。

| 端点 | 方法 | 描述 |
|------|------|------|
| `/api/agent/schema` | GET | 获取指定类型的字段定义和校验规则 |
| `/api/agent/check-duplicate` | GET | 检查是否已存在相同地区+日期+类型的政策 |
| `/api/agent/policies` | GET | 查询已发布的政策 |
| `/api/agent/submit` | POST | 提交政策数据到审核队列 |
| `/api/agent/submissions` | GET | 跟踪提交的审核状态 |

认证：`Authorization: Bearer <api_key>`

详细工作流和字段说明见 [AGENTS.md](./AGENTS.md)。

---

## 技术栈

| 层级 | 技术 |
|------|------|
| 后端框架 | Python 3.11 + FastAPI (async) |
| ORM | SQLAlchemy 2.0 (async) |
| 数据库 | SQLite + aiosqlite (WAL 模式) |
| 前端框架 | React 18 + TypeScript |
| 构建工具 | Vite 5 |
| UI 组件 | Ant Design 5 |
| 状态管理 | Zustand |
| HTTP 客户端 | Axios |
| 容器 | Docker（多阶段构建，non-root 运行） |
| CI/CD | GitHub Actions → GHCR |

---

## 开发命令

```bash
# 后端
python run.py                          # 启动开发服务器（DEBUG=true 时热重载）
pytest                                 # 运行全部测试
pytest tests/test_main.py::test_health -v  # 运行单个测试

# 前端
cd web
npm run dev                            # 启动开发服务器（端口 3000）
npm run build                          # 构建生产版本到 web/dist/
```

## License

MIT

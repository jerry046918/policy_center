# Policy Center - 政策数据管理平台

政策数据管理平台，用于管理全国31个省级行政区（332个地级市）的多类型政策（社保基数、公积金基数、平均工资、人才政策等）。

## 功能特性

- **政策管理**: 支持社保基数上下限、公积金基数、平均工资、人才政策等多种类型，支持追溯缴纳等业务逻辑
- **审核流程**: Agent 提交 → AI 辅助校验 → 人工审核 → 发布
- **版本管理**: 完整的版本历史、变更追踪、回滚支持
- **地区管理**: 内置全国31省份及332个地级市的行政区划数据
- **Agent REST API**: 标准化 REST API 支持外部 Agent 接入

## 快速开始

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
# 编辑 .env，修改 JWT_SECRET_KEY
```

### 3. 启动服务

```bash
# 一键启动前后端 + 自动创建测试 Agent
python start.py

# 或者分别启动：
# 后端
python run.py
# 前端（新终端）
cd web && npm run dev
```

### 4. 访问

- **前端界面**: http://localhost:3000 (start.py) 或 http://localhost:5173 (npm run dev)
- **API 文档**: http://localhost:8000/docs
- **默认登录**: admin / admin123
- **测试 Agent API Key**: `pk_test_1234567890abcdef1234567890abcdef` (start.py 自动创建)

## Docker 部署

```bash
# 构建并启动
docker-compose up -d

# 查看日志
docker-compose logs -f

# 停止
docker-compose down
```

## 项目结构

```
policy_center/
├── app/                      # 后端代码
│   ├── api/                  # REST API 路由
│   │   ├── auth.py          # 认证登录
│   │   ├── policies.py      # 政策 CRUD
│   │   ├── reviews.py       # 审核中心
│   │   ├── admin.py         # 系统管理
│   │   ├── agent.py         # Agent API
│   │   └── dashboard.py     # 数据看板
│   ├── models/              # SQLAlchemy ORM 模型
│   ├── schemas/             # Pydantic 请求/响应模式
│   ├── services/            # 业务逻辑层
│   ├── utils/               # 工具函数
│   ├── config.py            # 配置管理
│   ├── database.py          # 数据库连接与初始化
│   └── main.py              # FastAPI 应用入口
├── web/                      # 前端代码（React + TypeScript + Vite）
│   └── src/
│       ├── components/      # 公共组件
│       ├── pages/           # 页面组件
│       ├── services/        # API 服务
│       ├── stores/          # Zustand 状态管理
│       └── types/           # TypeScript 类型定义
├── data/                     # 数据文件
│   ├── policy_center.db     # SQLite 数据库
│   └── regions.json         # 行政区划数据（31省 + 332市）
├── uploads/                  # 上传文件存储
├── tests/                    # 测试文件
├── requirements.txt          # Python 依赖
├── start.py                  # 一键启动脚本（前后端 + 测试 Agent）
├── run.py                    # 后端启动脚本
├── Dockerfile
├── docker-compose.yml
└── .env.example
```

## 数据初始化

系统首次启动时会自动初始化：

1. **创建数据库表结构**
2. **创建默认管理员账户** (admin / admin123)
3. **加载行政区划数据** (31省份 + 332地级市)

如需重新初始化地区数据，可调用 API：
```bash
curl -X POST "http://localhost:8000/api/v1/admin/regions/init?force=true" \
  -H "Authorization: Bearer <token>"
```

## Agent API

外部 Agent 可通过 REST API 提交政策数据：

| 端点 | 方法 | 描述 |
|------|------|------|
| `/api/agent/schema` | GET | 获取政策 Schema |
| `/api/agent/check-duplicate` | GET | 检查重复提交 |
| `/api/agent/policies` | GET | 查询已发布政策 |
| `/api/agent/submit` | POST | 提交政策到审核队列 |
| `/api/agent/submissions` | GET | 跟踪提交审核状态 |

认证方式：`Authorization: Bearer <api_key>`

## 技术栈

| 层级 | 技术 |
|------|------|
| 后端框架 | FastAPI |
| ORM | SQLAlchemy 2.0 (async) |
| 数据库 | SQLite (WAL 模式) |
| 缓存 | cachetools (内存) |
| 前端框架 | React 18 + TypeScript |
| 构建 | Vite |
| UI 组件 | Ant Design 5 |
| 状态管理 | Zustand |
| HTTP 客户端 | Axios |

## 开发命令

```bash
# 后端开发
python run.py                    # 启动开发服务器
pytest                           # 运行测试
pytest tests/test_main.py -v     # 运行单个测试

# 前端开发
cd web
npm run dev                      # 启动开发服务器
npm run build                    # 构建生产版本
```

## License

MIT

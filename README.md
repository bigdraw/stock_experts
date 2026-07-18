# 股票分析平台 (Stock Analysis Platform)

一个基于 AI 的 A 股分析平台，支持书籍学习生成投资 Agent、自然语言筛选、多 Agent 辩论、策略回测等功能。

## ✨ 核心功能

### 📚 书籍学习 → Agent 生成 (M3)
- 上传投资书籍（PDF/EPUB/TXT）
- LLM 自动分析全文，提取投资理念和策略框架
- 生成结构化的投资 Agent 定义
- 支持手动用自然语言定义 Agent

### 📊 股票数据采集 (M2)
- 覆盖 A 股 600/000/300 开头股票（~5000 只）
- **分层采集**：基础指标全量 + 深度数据按需
- **双层自愈**：规则引擎兜底 + LLM Agent 智能修复
- Provider 模式：默认 akshare（免费），支持切换付费 API

### 🔍 自然语言筛选 (M4)
- 自然语言描述筛选条件 → LLM 生成 Python 代码
- 持久化到工具库，下次直接调用（不走 LLM）
- 安全沙箱执行，防止恶意代码
- 可被组合构建和策略回测复用

### 💼 投资组合管理 (M6)
- 创建/编辑/删除多个投资组合
- 手动添加股票或通过筛选脚本批量添加
- 实时行情展示（日 K 线 + 基础指标）
- 多指标列表直观对比

### 📈 策略回测 (M7)
- 自然语言描述策略 → LLM 生成策略代码
- 支持个股回测、组合回测、全量选股+交易联合策略
- 摩擦成本可配置（默认 A 股标准：印花税 0.05%、佣金 0.025%、滑点 0.1%）
- 输出：收益率、最大回撤、夏普比率、胜率、资金曲线、交易明细

### 🗣️ 多 Agent 辩论 (M5)
- 加载多个不同风格的投资 Agent（巴菲特、索罗斯、弗利莫等）
- 针对指定股票或组合进行辩论分析
- 结构化辩论：分析 → 质疑 → 回应 → 总结
- 客观中立的 Agent 综合辩论结果输出分析报告

### 🔔 通知提醒 (M10)
- 用户自定义告警（自然语言描述条件）
- 系统运维提醒（数据库备份、采集异常等）
- 站内消息通知

## 🛠️ 技术栈

### 后端
- **框架**: FastAPI 0.139+
- **ORM**: SQLAlchemy 2.0 (async)
- **数据库**: SQLite（原型）→ PostgreSQL（生产）
- **数据采集**: akshare + Provider 接口
- **回测引擎**: 自研（pandas + numpy）
- **任务调度**: APScheduler 3.10+
- **认证**: JWT (python-jose)
- **包管理**: uv

### 前端
- **框架**: Vue 3.4+ + TypeScript
- **构建**: Vite 5
- **UI 组件**: Naive UI
- **图表**: ECharts 5 + vue-echarts
- **状态管理**: Pinia
- **路由**: Vue Router 4
- **HTTP**: Axios

### AI/LLM
- **默认模型**: qwen3.7-max（阿里云）
- **接口标准**: OpenAI 兼容 API
- **配置方式**: base_url + api_key，支持多 Provider 切换

## 📁 项目结构

```
stock/
├── .ai/                          # long-dev 框架文档
│   ├── STATUS.md                 # 当前状态指针
│   ├── ARCHITECTURE.md           # 架构总览
│   ├── ROADMAP.md                # 里程碑与任务清单
│   ├── REQUIREMENTS.md           # 需求规格
│   ├── ISSUES.md                 # 遗留问题
│   ├── decisions/                # 架构决策记录 (ADR)
│   └── modules/                  # 各模块设计文档
│       ├── m1-llm-provider/
│       ├── m2-data-acquisition/
│       ├── m3-book-learning/
│       ├── m4-nl-filter/
│       ├── m5-debate/
│       ├── m6-portfolio/
│       ├── m7-backtesting/
│       ├── m8-frontend/
│       ├── m9-backend/
│       └── m10-notification/
├── backend/                      # FastAPI 后端
│   ├── app/
│   │   ├── main.py               # 应用入口
│   │   ├── config.py             # 配置管理
│   │   ├── database.py           # 数据库连接
│   │   ├── models/               # SQLAlchemy ORM 模型
│   │   ├── schemas/              # Pydantic 请求/响应 schema
│   │   ├── api/v1/               # API 路由
│   │   │   ├── auth.py           # 认证
│   │   │   ├── stocks.py         # 股票数据
│   │   │   ├── portfolios.py     # 投资组合
│   │   │   ├── filters.py        # 筛选脚本
│   │   │   ├── backtest.py       # 回测
│   │   │   ├── debate.py         # 辩论
│   │   │   ├── books.py          # 书籍管理
│   │   │   ├── notifications.py  # 通知
│   │   │   └── data.py           # 数据采集
│   │   ├── services/             # 业务逻辑
│   │   │   ├── llm/              # M1: LLM Provider
│   │   │   ├── data/             # M2: Data Acquisition
│   │   │   ├── book/             # M3: Book Learning
│   │   │   ├── filter/           # M4: NL → Filter
│   │   │   ├── debate/           # M5: Multi-Agent Debate
│   │   │   ├── portfolio/        # M6: Portfolio
│   │   │   ├── backtest/         # M7: Backtesting
│   │   │   └── notification/     # M10: Notification
│   │   ├── scheduler/            # 定时任务
│   │   └── utils/                # 工具函数
│   ├── data/                     # SQLite 数据库文件
│   ├── config.yaml               # 运行时配置
│   ├── config.example.yaml       # 配置模板
│   └── pyproject.toml            # Python 依赖
├── frontend/                     # Vue 3 前端
│   ├── src/
│   │   ├── main.ts               # 应用入口
│   │   ├── App.vue               # 根组件
│   │   ├── router/               # 路由配置
│   │   ├── stores/               # Pinia 状态管理
│   │   ├── api/                  # API 客户端
│   │   ├── views/                # 页面组件
│   │   │   ├── Login.vue
│   │   │   ├── Dashboard.vue
│   │   │   ├── StockList.vue
│   │   │   ├── StockDetail.vue
│   │   │   ├── PortfolioList.vue
│   │   │   ├── PortfolioDetail.vue
│   │   │   ├── FilterLibrary.vue
│   │   │   ├── BacktestCreate.vue
│   │   │   ├── BacktestResult.vue
│   │   │   ├── DebateCreate.vue
│   │   │   ├── BookManager.vue
│   │   │   ├── AlertManager.vue
│   │   │   └── Settings.vue
│   │   ├── components/           # 通用组件
│   │   │   ├── layout/           # 布局组件
│   │   │   ├── charts/           # 图表组件
│   │   │   └── common/           # 通用 UI 组件
│   │   └── types/                # TypeScript 类型
│   ├── vite.config.ts            # Vite 配置
│   └── package.json              # Node 依赖
└── scripts/                      # 启动/停止脚本
    ├── start-services.ps1        # 启动服务 (PowerShell)
    ├── stop-services.ps1         # 停止服务 (PowerShell)
    ├── start-services.bat        # 启动服务 (双击运行)
    └── stop-services.bat         # 停止服务 (双击运行)
```

## 🚀 快速开始

### 环境要求

- **Python**: 3.12+
- **Node.js**: 18+
- **uv**: Python 包管理器（[安装指南](https://docs.astral.sh/uv/getting-started/installation/)）
- **npm**: Node 包管理器（随 Node.js 一起安装）

### 1. 克隆项目

```bash
git clone <repository-url>
cd stock
```

### 2. 安装依赖

```bash
# 后端依赖
cd backend
uv sync

# 前端依赖
cd ../frontend
npm install
```

### 3. 配置 LLM API Key

编辑 `backend/config.yaml`：

```yaml
llm:
  default_provider: "qwen"
  providers:
    qwen:
      base_url: "https://dashscope.aliyuncs.com/compatible-mode/v1"
      api_key: "your-api-key-here"  # 替换为你的 API Key
      model: "qwen3.7-max"
```

或者使用环境变量：

```bash
export LLM_API_KEY="your-api-key-here"
```

### 4. 启动服务

#### 方式一：使用启动脚本（推荐）

```powershell
# PowerShell
.\scripts\start-services.ps1

# 或双击运行
scripts\start-services.bat
```

#### 方式二：手动启动

```bash
# 终端 1：启动后端
cd backend
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload

# 终端 2：启动前端
cd frontend
npm run dev
```

### 5. 访问应用

- **前端界面**: http://127.0.0.1:5173
- **后端 API**: http://127.0.0.1:8000
- **API 文档**: http://127.0.0.1:8000/docs

### 6. 停止服务

```powershell
# PowerShell
.\scripts\stop-services.ps1

# 或双击运行
scripts\stop-services.bat
```

## ⚙️ 配置说明

### 后端配置 (`backend/config.yaml`)

```yaml
server:
  host: "0.0.0.0"
  port: 8000
  cors_origins:
    - "http://localhost:5173"

database:
  url: "sqlite+aiosqlite:///./data/stock.db"

auth:
  secret_key: "change-me-in-production"
  token_expire_minutes: 1440

llm:
  default_provider: "qwen"
  providers:
    qwen:
      base_url: "https://dashscope.aliyuncs.com/compatible-mode/v1"
      api_key: "${LLM_API_KEY}"
      model: "qwen3.7-max"

data_source:
  default_provider: "akshare"
  providers:
    akshare:
      rate_limit: 10
      retry_max: 3

backtest:
  friction:
    stamp_tax: 0.0005       # 印花税 0.05%（卖出单边）
    commission: 0.00025     # 佣金 0.025%（买卖各）
    commission_min: 5.0     # 最低佣金 5 元
    slippage: 0.001         # 滑点 0.1%

scheduler:
  daily_update_time: "16:30"
  backup_day: "sunday"
```

### 前端配置 (`frontend/vite.config.ts`)

```typescript
export default defineConfig({
  plugins: [vue()],
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
})
```

## 📖 使用指南

### 1. 注册和登录

访问 http://127.0.0.1:5173，点击"注册"创建新用户，然后登录。

### 2. 数据采集

登录后进入仪表盘，点击"全量采集基础指标"或"增量更新"按钮启动数据采集任务。

### 3. 创建筛选脚本

进入"筛选工具库"页面：
1. 输入筛选脚本名称（如"高 ROE 低 PE"）
2. 用自然语言描述筛选条件（如"ROE 大于 15% 且市盈率小于 20 的盈利股票"）
3. 点击"生成"按钮
4. 生成的脚本会保存到工具库，可重复使用

### 4. 构建投资组合

进入"投资组合"页面：
1. 点击"创建组合"
2. 输入组合名称和描述
3. 进入组合详情，手动添加股票或通过筛选脚本批量添加

### 5. 策略回测

进入"策略回测"页面：
1. 输入策略名称和自然语言描述（如"均线交叉策略：5 日均线上穿 20 日均线买入，下穿卖出"）
2. 点击"生成策略代码"
3. 配置回测参数（股票代码、日期范围、初始资金）
4. 点击"执行回测"
5. 查看回测结果：收益率、最大回撤、夏普比率、胜率、资金曲线

### 6. 多 Agent 辩论

进入"辩论分析"页面：
1. 选择至少 2 个投资 Agent（如"巴菲特"和"索罗斯"）
2. 输入分析标的（股票代码，如 600519）
3. 设置辩论轮数（默认 3 轮）
4. 点击"开始辩论"
5. 查看辩论过程和总结报告

### 7. 书籍学习

进入"书籍管理"页面：
1. 上传投资书籍（PDF/EPUB/TXT）
2. 点击"生成投资 Agent"
3. LLM 会分析全书，提取投资理念，生成 Agent 定义
4. 生成的 Agent 可用于辩论分析

## 🏗️ 架构设计

### 模块划分

| 模块 | 职责 | 依赖 |
|------|------|------|
| M1: LLM Provider | 统一 LLM 调用接口 | 无 |
| M2: Data Acquisition | 股票数据采集 | M1 |
| M3: Book Learning | 书籍学习 → Agent 生成 | M1 |
| M4: NL → Filter | 自然语言 → 筛选脚本 | M1, M2 |
| M5: Multi-Agent Debate | 多 Agent 辩论 | M1, M3 |
| M6: Portfolio | 投资组合管理 | M2, M4 |
| M7: Backtesting | 策略回测 | M1, M2, M4 |
| M8: Frontend | 前端界面 | M9 |
| M9: Backend API | 后端服务 | M1-M7, M10 |
| M10: Notification | 通知提醒 | M1, M2, M9 |

### 核心设计决策

详见 `.ai/decisions/` 目录：

- **ADR-001**: NL→Code 管线作为核心模式
- **ADR-002**: 双层自愈机制（规则引擎 + LLM Agent）
- **ADR-003**: Provider 模式管理外部依赖
- **ADR-004**: 安全沙箱执行 LLM 生成代码
- **ADR-005**: 分层数据采集策略

## 🔧 开发指南

### 后端开发

```bash
cd backend

# 安装依赖
uv sync

# 启动开发服务器（热重载）
uv run uvicorn app.main:app --reload

# 运行测试
uv run pytest

# 代码格式化
uv run ruff format .
uv run ruff check . --fix
```

### 前端开发

```bash
cd frontend

# 安装依赖
npm install

# 启动开发服务器
npm run dev

# 构建生产版本
npm run build

# 代码检查
npm run lint

# 类型检查
npm run type-check
```

### 添加新模块

1. 在 `.ai/modules/` 下创建模块目录和 `DESIGN.md`
2. 在 `backend/app/services/` 下实现业务逻辑
3. 在 `backend/app/api/v1/` 下添加 API 路由
4. 在 `backend/app/api/v1/__init__.py` 中注册路由
5. 在 `frontend/src/views/` 下创建页面组件
6. 在 `frontend/src/router/index.ts` 中添加路由
7. 更新 `.ai/ROADMAP.md` 和 `.ai/STATUS.md`

## 📝 API 文档

启动后端后访问 http://127.0.0.1:8000/docs 查看完整的 Swagger API 文档。

### 主要 API 端点

| 模块 | 端点前缀 | 说明 |
|------|----------|------|
| 认证 | `/api/v1/auth` | 登录、注册、获取当前用户 |
| 股票 | `/api/v1/stocks` | 股票列表、详情、行情、财报 |
| 组合 | `/api/v1/portfolios` | 组合 CRUD、股票管理 |
| 筛选 | `/api/v1/filters` | 筛选脚本生成、执行、管理 |
| 回测 | `/api/v1/backtest` | 策略生成、回测执行、结果查询 |
| 辩论 | `/api/v1/debate` | 辩论启动、结果查询 |
| 书籍 | `/api/v1/books` | 书籍上传、Agent 生成 |
| 通知 | `/api/v1/notifications` | 通知列表、告警管理 |
| 数据 | `/api/v1/data` | 数据采集任务管理 |

## 🐛 已知问题

详见 `.ai/ISSUES.md`：

- **ISSUE-001**: M2 双层自愈的 LLM Agent 层未完整实现（高优先级）
- **ISSUE-002**: M4 语义匹配精度有限（中优先级）
- **ISSUE-003**: 前端 API 错误边界不完整（中优先级）
- **ISSUE-004**: 回测选股联合策略集成度不够（中优先级）
- **ISSUE-005**: 数据采集缺少数据校验层（高优先级）
- **ISSUE-006**: M10 WebSocket 实时推送未实现（低优先级）

## 📅 开发路线图

详见 `.ai/ROADMAP.md`：

- ✅ **M1**: long-dev 框架脚手架
- ✅ **M2**: stock 工程需求 kickoff
- ✅ **M3**: stock 工程实现（当前）
- ⏳ **待规划**: 
  - 引入 SQLite 作为派生索引
  - 飞书/云部署/小程序扩展渠道
  - 完善 LLM Agent 自愈机制
  - 优化语义匹配和错误处理

## 🤝 贡献指南

1. Fork 项目
2. 创建功能分支 (`git checkout -b feature/AmazingFeature`)
3. 提交更改 (`git commit -m 'Add some AmazingFeature'`)
4. 推送到分支 (`git push origin feature/AmazingFeature`)
5. 开启 Pull Request

## 📄 许可证

本项目仅供学习和研究使用。

## 🙏 致谢

- [FastAPI](https://fastapi.tiangolo.com/) - 现代、快速的 Web 框架
- [Vue.js](https://vuejs.org/) - 渐进式 JavaScript 框架
- [Naive UI](https://www.naiveui.com/) - Vue 3 组件库
- [ECharts](https://echarts.apache.org/) - 开源可视化图表库
- [akshare](https://akshare.akfamily.xyz/) - 开源财经数据接口
- long-dev - 本项目自研的长任务开发框架（详见 `.opencode/skills/long-dev/`）

## 📞 联系方式

如有问题或建议，请提交 Issue 或联系开发者。

---

**注意**: 本项目仅供学习和研究使用，不构成任何投资建议。投资有风险，入市需谨慎。

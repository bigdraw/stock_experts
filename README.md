# 📈 Stock Analysis Platform | AI 驱动的 A 股价值投资分析平台

> 数据驱动的价值投资分析平台——6 维评估框架、9 位投资大师 Agent、历史K线+周期切换、策略回测、风险看板、Agent 工具发现。

<!-- 截图位（后续补充）
![Dashboard](docs/screenshots/dashboard.png)
![StockDetail](docs/screenshots/stock-detail.png)
![Value Analysis](docs/screenshots/value-analysis.png)
-->

## ✨ 核心功能

### 💬 对话式主页 + Agent 交互
- 登录后落地页为**对话窗口**（ChatGPT 式）
- `@巴菲特 @格雷厄姆 分析 600519`——@提及多个 Agent 对话
- `/value_analysis`——/ 列出可用技能
- **快捷操作按钮**（个股分析/组合管理/组合分析/策略回测/辩论/筛选）
- **MCP 工具端点**：`POST /chat/analyze/stock`（个股分析，验证存在+取价值分析数据）、`POST /chat/analyze/portfolio`（组合分析+风险看板）、`POST /chat/analyze/fund`（场内ETF+场外基金）
- 自动检测消息中的股票代码 → 自动取价值分析数据注入 LLM 上下文

### 🔬 价值投资分析（6 维框架）
一次性获取个股的完整价值画像：
- **估值**：PE / PB / PS / PCF / Graham number / 股息率 / FCF yield
- **盈利能力**：ROE / ROA / ROIC / 毛利率 / 净利率（+ 近 3 年/10 年均值）
- **财务安全**：资产负债率 / 流动比率 / 现金比率 / 利息保障倍数
- **现金流**：经营现金流 OCF / 自由现金流 FCF / FCF 收益率 / 盈利质量（OCF/净利）
- **成长性**：营收/净利/净资产 CAGR（3 年/5 年）
- **分红真实性**：股息率 / 派息率 / 连续派息年数 / 分红增速

### 📊 历史 K 线 + 周期切换
- **全量历史**（从 2010 年起，按需拉取并缓存到本地 DB）
- **周期切换**：日 K / 周 K / 月 K / 季 K / 年 K（pandas resample，本地秒切）
- 多数据源容错：东方财富主源 + 新浪 fallback（不因单源抽风而缺数据）

### 🤖 9 位投资大师 Agent（平台默认）
内置 8 位经典 + 1 位现代价值分析 Agent：
- 巴菲特 / 芒格 / 彼得·林奇 / 索罗斯 / 塔勒布 / 利弗莫尔 / 格雷厄姆 / 费雪
- **现代价值分析**（6 维 + 分红真实性 + 现代思路：百分位估值/所有者收益/反脆弱检查/杜邦分解）
- 每个 Agent 的 system_prompt 内置可用工具描述（平台数据 + 联网搜索）
- 支持用户从**文本输入**或**拖拽文件**自定义构造 Agent

### 🎯 Agent 工具发现 + 联网搜索
- `GET /agent/tools`：列出所有分析端点（价值分析/行情/K线/财报/回测/风险/信号/选股）
- `GET /agent/web-search?q=...`：联网搜索（tavily 优先，无 key 降级 DuckDuckGo）
- Agent 据此自行取数 + 得出结论，工具不替 Agent 下结论

### 📈 策略回测（纯 pandas，无重依赖）
- 9 个结构化策略模板（SMA/EMA/MACD/RSI/Bollinger/Momentum/Mean Reversion/Breakout/Volume Momentum）
- 自然语言 → 策略参数解析
- 服务端取数回测（选策略+股票+区间 → 权益曲线+指标）
- 滚动样本外（walk-forward）+ 蒙特卡洛置信区间
- 移植自 maverick-mcp（MIT），纯 pandas/numpy 重写（无 vectorbt 依赖）

### 💼 组合管理 + 风险看板
- 持仓管理 + N+1 优化批量取数
- VaR95/99 + 行业集中度 + 加仓前模拟 + regime 调整仓位
- 可解释三策略选股打分（bullish/bearish/supply_demand）

### 🗣️ 多 Agent 辩论
- 加载多个不同风格的投资 Agent，针对股票/组合辩论
- 结构化：分析 → 质疑 → 回应 → 总结

### 🌐 多语言支持
- 中/英/日/韩 切换（localStorage 持久）
- 轻量自建 i18n（无 vue-i18n 依赖）

### 🏢 公司信息
- 同花顺爬虫提取公司简介/行业/板块（不用 LLM 生成）
- 主源 10jqka + 新浪 F10 备选

### 🔐 安全增强
- 注册：邮箱ID + 用户名 + 邮箱唯一 + 用户名重名 + 密码 ≥8 位
- 登录：支持邮箱/用户名 + 5 次错误锁定 15 分钟
- JWT 鉴权 + require_admin 门控 + RestrictedPython 沙箱

### 📝 README 刷新约定
- AGENTS.md：每次大更新后自动判断并刷新 README

## 🚀 快速开始

<!-- 演示动图位（后续补充）
![Demo](docs/screenshots/demo.gif)
-->

### 后端
```bash
cd backend
uv sync                          # 安装依赖
cp config.example.yaml config.yaml  # 复制配置模板
export AUTH_SECRET_KEY=$(python -c "import secrets;print(secrets.token_urlsafe(64))")
export LLM_API_KEY=your-api-key     # LLM API key (qwen/dashscope)
uv run uvicorn app.main:app --reload --port 8000
```

### 前端
```bash
cd frontend
npm install
npm run dev                      # http://localhost:5173
```

### 测试
```bash
cd backend && uv run pytest -q   # 7 个测试文件
cd frontend && npx vue-tsc --noEmit  # 类型检查
```

## 🏗️ 技术栈

| 层 | 技术 |
|---|---|
| 后端 | FastAPI + SQLAlchemy 2 (async) + APScheduler + aiosqlite |
| 前端 | Vue 3 + TypeScript + Naive UI + ECharts + Pinia |
| 数据源 | akshare (Sina/Eastmoney) + stock_financial_report_sina (三大报表) |
| LLM | OpenAI 兼容协议（qwen/dashscope 默认，DB 存配置 + reload） |
| 沙箱 | RestrictedPython（LLM 生成代码安全执行） |
| 回测 | 纯 pandas/numpy（移植自 maverick-mcp, MIT） |

## 📁 项目结构
```
backend/
├── app/
│   ├── api/v1/          # 路由（stocks/quant/agent/backtest/...）
│   ├── services/
│   │   ├── data/        # 数据采集+缓存+价值分析+三大报表
│   │   ├── backtesting/  # 纯pandas回测引擎（移植 maverick）
│   │   ├── signals/      # 信号条件引擎+市场状态识别
│   │   ├── screening/     # 三策略可解释选股
│   │   ├── journal/       # 交易日志+策略表现
│   │   ├── risk/          # 风险看板（VaR/集中度/pre-trade）
│   │   ├── audit/         # DecisionLog 审计
│   │   └── technical/     # 纯pandas技术指标（SMA/EMA/RSI/MACD/ATR）
│   ├── scheduler/         # 自动调度（日增量/月财报/启动决策）
│   └── scripts/masters/   # 9位投资大师理念文件（各自独立.md）
├── tests/                # 7个测试文件
└── scripts/              # seed_master_agents 等

frontend/
├── src/
│   ├── views/            # 页面（StockDetail/Dashboard/Agent构建/...）
│   ├── api/              # API client
│   └── stores/           # Pinia stores
└── e2e/                  # Playwright E2E
```

## 🔒 安全
- JWT 鉴权 + `require_admin` 门控（数据采集/设置/审计 admin-only）
- 凭据不入 git（`${VAR}` 环境变量插值，config.yaml gitignored）
- RestrictedPython 沙箱（LLM 代码安全执行 + dunder 逃逸阻断）
- HTTP-only token + SSE Authorization header（token 不进 URL）

## 📄 License
平台代码自有版权。移植自 [maverick-mcp](https://github.com/wshobson/maverick-mcp) 的模块（MIT, Copyright (c) 2024）在文件头署名。

## 🙏 致谢
- [maverick-mcp](https://github.com/wshobson/maverick-mcp) (MIT) — 回测/信号/选股/风险/日志/指标模块的移植来源
- [akshare](https://github.com/akfamily/akshare) — A 股数据源
- [opencode](https://github.com/sst/opencode) — AI 开发框架

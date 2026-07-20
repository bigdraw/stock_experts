[中文](README.md) | [English](README.en.md) | [日本語](README.ja.md) | [한국어](README.ko.md)

# 🧠 不是又一个股票软件，而是你的 AI 价值投资分析平台

> @巴菲特 分析 600519 —— 一句话，大师 Agent 自动取数、6 维体检、给出结论。股票软件千千万，能把"投资大师"装进对话窗口的，只有这一个。

<!-- 截图位：对话主页 + @大师 + 估值带
![Chat Home](docs/screenshots/chat-home.png)
![Value Analysis](docs/screenshots/value-analysis.png)
-->

## 🎯 为什么用我们

市面上的股票软件要么是冷冰冰的数据终端，要么是只会画K线的看盘工具。我们做的不是"看盘"——是**让 AI 像投资大师一样替你思考**：

- **9 位投资大师 Agent 常驻对话**：巴菲特 / 芒格 / 彼得·林奇 / 索罗斯 / 塔勒布 / 利弗莫尔 / 格雷厄姆 / 费雪 + 现代价值分析 Agent，每位都有独立理念文件与可用工具
- **6 维价值投资框架**：估值 / 盈利能力 / 财务安全 / 现金流 / 成长性 / 分红真实性——一次性给个股完整价值画像，不是只看 PE
- **对话式交互**：`@巴菲特 @格雷厄姆 分析 600519` 多 Agent 同框、`/` 列出全部技能、自然语言驱动回测——没有菜单迷宫
- **ChatGPT 式多会话**：侧边栏会话管理、独立上下文记忆、**流式 SSE 输出**（逐字呈现）、**服务端上下文压缩**（超阈值自动摘要，参考 LobeChat 算法）、Markdown 渲染 + 代码高亮

## ✨ 特色亮点

- 💬 **@大师 + 自动取数**：消息里写股票代码，平台自动拉取价值分析数据注入 LLM 上下文，大师 Agent 据此下结论，工具不替 Agent 思考
- 📊 **P/E P/B P/S 估值带**：百分位视角看贵不贵，不再只看绝对数
- 📈 **K 线全量历史 + 周期切换**：2010 年至今全量数据，日/周/月/季/年K本地秒切（pandas resample）
- 🏢 **同花顺爬虫公司信息**：真实公司简介/行业/板块，不用 LLM 编造
- 🧪 **一键回测**：9 个策略模板 + 自然语言参数 + 滚动样本外 + 蒙特卡洛置信区间
- 🐼 **纯 pandas 回测引擎**：无 vectorbt 重依赖，移植自 maverick-mcp（MIT），轻量可信
- 🌐 **中 / 英 / 日 / 韩 四语言**：轻量自建 i18n，localStorage 持久

## 🧭 还能做什么

- 💼 **组合管理 + 风险看板**：VaR95/99、行业集中度、加仓前模拟、regime 调仓
- 🗣️ **多 Agent 辩论**：让不同风格的大师对一只股票/一个组合互相质疑、回应、总结
- 🎯 **可解释三策略选股**：bullish / bearish / supply_demand 打分，黑箱 bye bye
- 🔌 **Agent 工具发现**：`GET /agent/tools` 列出全部端点，`GET /agent/web-search` 联网搜索

## 🚀 上手三步

```bash
# 后端
cd backend && uv sync
cp config.example.yaml config.yaml
export LLM_API_KEY=your-key
uv run uvicorn app.main:app --reload --port 8000

# 前端
cd frontend && npm install && npm run dev   # http://localhost:5173
```

打开前端，在对话里输入 `@巴菲特 分析 600519`，开始你的价值投资之旅。

<!-- 演示动图位（后续补充）
![Demo](docs/screenshots/demo.gif)
-->

## 📄 License & 致谢

平台代码自有版权。回测/信号/选股/风险模块移植自 [maverick-mcp](https://github.com/wshobson/maverick-mcp) (MIT, Copyright (c) 2024)，文件头署名。数据源 [akshare](https://github.com/akfamily/akshare)。

[中文](README.md) | [English](README.en.md) | [日本語](README.ja.md) | [한국어](README.ko.md)

# 🧠 Not just another stock app — your AI value-investing analysis platform

> @Buffett analyze 600519 — one line, and the Master Agent fetches the data, runs a 6-dimension checkup, and gives the verdict. There are a thousand stock apps; this is the only one that puts the great investors inside your chat window.

<!-- Screenshot slot: chat home + @master + valuation band
![Chat Home](docs/screenshots/chat-home.png)
![Value Analysis](docs/screenshots/value-analysis.png)
-->

## 🎯 Why us

Most stock apps are either cold data terminals or chart-only viewers. We don't do "watching the market" — we make **AI think like the great investors**:

- **9 Master Agents live in your chat**: Buffett / Munger / Peter Lynch / Soros / Taleb / Livermore / Graham / Fisher + a Modern Value Agent — each with its own philosophy file and toolset
- **6-dimension value-investing framework**: Valuation / Profitability / Financial Safety / Cash Flow / Growth / Dividend Authenticity — a full value portrait in one shot, not just PE
- **Conversational interaction**: `@Buffett @Graham analyze 600519` for multi-agent collaboration, `/` to list all skills, natural-language-driven backtesting — no menu mazes

## ✨ Highlights

- 💬 **@Master + auto data fetch**: drop a ticker in your message, the platform auto-pulls value-analysis data into the LLM context; the Master Agent draws the conclusion, tools don't think for it
- 📊 **P/E P/B P/S valuation bands**: percentile view of "is it cheap" — no more staring at absolute numbers
- 📈 **Full K-line history + period switch**: all data since 2010, day/week/month/quarter/year resampled locally in seconds (pandas resample)
- 🏢 **Tonghuashun crawler for company info**: real company profiles / industries / sectors — no LLM fabrication
- 🧪 **One-click backtest**: 9 strategy templates + natural-language params + walk-forward + Monte Carlo confidence intervals
- 🐼 **Pure pandas backtesting engine**: no heavy vectorbt dependency, ported from maverick-mcp (MIT), lightweight and trustworthy
- 🌐 **CN / EN / JA / KO four languages**: lightweight home-built i18n, persisted in localStorage

## 🧭 Also does

- 💼 **Portfolio management + risk dashboard**: VaR95/99, industry concentration, pre-trade simulation, regime-based sizing
- 🗣️ **Multi-agent debate**: let masters of different styles challenge, respond, and summarize over a stock or portfolio
- 🎯 **Explainable 3-strategy screening**: bullish / bearish / supply_demand scoring — goodbye black boxes
- 🔌 **Agent tool discovery**: `GET /agent/tools` lists all endpoints; `GET /agent/web-search` for live search

## 🚀 Three steps to start

```bash
# Backend
cd backend && uv sync
cp config.example.yaml config.yaml
export LLM_API_KEY=your-key
uv run uvicorn app.main:app --reload --port 8000

# Frontend
cd frontend && npm install && npm run dev   # http://localhost:5173
```

Open the frontend, type `@Buffett analyze 600519` in the chat, and start your value-investing journey.

<!-- Demo gif slot (to be added)
![Demo](docs/screenshots/demo.gif)
-->

## 📄 License & Credits

Platform code is proprietary. Backtesting / signals / screening / risk modules are ported from [maverick-mcp](https://github.com/wshobson/maverick-mcp) (MIT, Copyright (c) 2024), credited in file headers. Data via [akshare](https://github.com/akfamily/akshare).

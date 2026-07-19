# maverick 移植说明书（小白向）

> 本文讲清楚：每个从 maverick-mcp 移植来的模块**做什么（what）、怎么用（how）、为什么需要（why）**。
> 面向不熟悉量化/AI 框架的同学。所有移植代码都在 `backend/app/services/` 下，MIT 协议（Copyright (c) 2024 wshobson，已在每个文件头署名）。
> 每个模块都带测试，在 `backend/tests/` 下，可用 `uv run pytest -q` 跑全部。

## 0. 先看全景：移植了什么

| # | 模块 | 路径 | 一句话 | 依赖 |
|---|---|---|---|---|
| 1 | 技术指标 | `app/services/technical/indicators.py` | SMA/EMA/RSI/MACD/ATR 纯公式实现 | 纯 pandas/numpy |
| 2 | 信号条件引擎 | `app/services/signals/conditions.py` | "RSI<30 且上穿"这类条件求值 | 上面的指标 |
| 3 | 市场状态 | `app/services/signals/regime.py` | 识别牛/熊/震荡/转换 | 纯 pandas |
| 4 | 选股打分 | `app/services/screening/` | 三套可解释打分选股 | 上面的指标 |
| 5 | 交易日志 | `app/services/journal/` | 记交易+按策略聚合表现 | async SQLAlchemy |
| 6 | 风险看板 | `app/services/risk/service.py` | VaR/集中度/加仓前模拟 | 纯数学 |
| 7 | 决策审计 | `app/services/audit/` | 记每条 agent/LLM 决策与成本 | async SQLAlchemy |
| 8 | 回测 | `app/services/backtesting/` | 策略回测/滚动外验/蒙特卡洛 | 纯 pandas/numpy |
| 9 | 信号↔回测 | `app/services/signals/backtest_adapter.py` | 把告警条件当策略回放 | 2 + 8 |

**关键诚实声明**：maverick 的**回测引擎层依赖 vectorbtpro（付费）**，免费 vectorbt 在 Python 3.12 上因 numba/llvmlite 装不上。所以我**没有照搬 vectorbt**，而是用纯 pandas/numpy 重写了**等价的最小组合模拟器**（第 8 节）。算法（信号生成、滚动外验、蒙特卡洛重采样）是可移植的，引擎调用本身不可移植——这点要说清楚，避免你以为"vectorbt 也能用"。

---

## 1. 技术指标 `technical/indicators.py`

**what**：用纯数学公式算 5 个最常用的技术指标——
- SMA（简单移动平均）、EMA（指数移动平均）、RSI（相对强弱）、MACD（异同均线）、ATR（真实波幅）。

**why**：算这些指标通常用 `pandas_ta` 或 `TA-Lib`，但它们要么要编译（TA-Lib 要 C 库）、要么版本坑多。maverick 用纯 pandas/numpy 把公式重写了一遍（逐项对照 pandas-ta 的 `talib=False` 公式），**零编译依赖、行为可复现**。我们平台本来就没有独立 TA 模块，正好补上。

**how**：
```python
import pandas as pd
from app.services.technical.indicators import sma, ema, rsi, macd, atr

close = your_close_series  # pd.Series，每行一个收盘价
sma20 = sma(close, 20)          # 20 日均线，前 19 行为 NaN
ema12 = ema(close, 12)          # 12 日指数均线
rsi14 = rsi(close, 14)         # 14 日 RSI，0-100
m = macd(close)                # DataFrame: macd/signal/histogram 三列
atr14 = atr(high, low, close, 14)  # 14 日真实波幅，需 high/low
```
**怎么验证**：`uv run python -m tests.test_indicators`（10 项断言：warmup NaN、种子值、RSI 有界、MACD histogram 恒等、ATR 正性、持平序列 RSI=50）。

---

## 2. 信号条件引擎 `signals/conditions.py`

**what**：把"告警"从"价格<X"升级为统一的**条件模型 + 跨次状态**。一个条件是一个 dict：
```python
{"indicator": "rsi", "operator": "crosses_above", "threshold": 50, "period": 14}
```
支持的 indicator：`price / rsi / volume / sma`；operator：`lt/gt/lte/gte/spike/crosses_above/crosses_below`。

**why**：原来的告警只能"价格<X"，无法表达"RSI 上穿 50""成交量异常放大 N 个标准差""价格跌破均线"。更关键的是 **`crosses_above/crosses_below` 是有状态的**——"上穿"必须知道上一根 bar 在线下、这根在线上，所以要跨 bar 传递 `previous_state`。这个引擎把状态管理封装好了。

**how**：
```python
from app.services.signals.conditions import evaluate_condition

cond = {"indicator": "rsi", "operator": "crosses_above", "threshold": 50, "period": 14}
result = evaluate_condition(cond, df, previous_state=last_state)
# result = {"triggered": True/False, "current_value": 52.3, "new_state": {...}, "error": None}
# 持久化 new_state，下次调用传进来
```
**怎么验证**：移植时 smoke 测试了 price-gt / rsi-spike / crosses 状态传递。

---

## 3. 市场状态 `signals/regime.py`

**what**：把市场分成 4 态——`bull（牛）/bear（熊）/choppy（震荡）/transitional（转换）`，并给置信度。4 个加权因子：趋势(0.35)+波动(0.25)+动量(0.25)+广度(0.15)。

**why**：不同市场要用不同策略（牛市跟趋势、熊市减仓、震荡做均值回归）。这个识别器驱动后面的"风险看板按 regime 调仓位"。

**how**：
```python
from app.services.signals.regime import RegimeDetector
r = RegimeDetector().classify(market_prices=hs300_close, vix_level=18, breadth_ratio=0.6)
# r = {"regime": "bull", "confidence": 0.72, "drivers": {...}, "votes": {...}}
```
A股没有官方 VIX，可用沪深 300 的 ATR 派生波动率代理；广度用涨跌家数比。

---

## 4. 选股打分 `screening/`

**what**：三套**可解释**的选股策略——
- `bullish`：多头动量（close 在 SMA50/150/200 之上、均线对齐、放量、RSI 未超买）
- `bearish`：空头（close 在均线之下、RSI 超卖/弱势、MACD 空头、高量下跌、ATR 收缩）
- `supply_demand`：供需突破（均线全对齐+上突破，基础 50 分 + 量能 + 接近 52 周高）

每条结果带 `flags`（哪些条件触发）+ `combined_score` + **`reason`（人类可读原因，如"bullish screen: close above SMA50, close above SMA200, ..."）**。

**why**：NL 自然语言选股灵活但不可解释、不稳定。这三套是经典结构化策略，作**可解释兜底**——每只股为什么入选，一目了然，可审计。

**how**：
```python
from app.services.screening.screens import score_bullish, score_bearish, score_supply_demand
from app.services.screening.config import get_screening_settings
s = get_screening_settings()
result = score_bullish("600519", df_with_close_volume, s)  # 返回 ScreeningResult 或 None
print(result.combined_score, result.reason)  # 75, "bullish screen: close above SMA50, ..."
```

---

## 5. 交易日志 + 策略表现 `journal/`

**what**：两张表——
- `journal_entries`：每笔交易（symbol/side/entry/exit/shares/**tags**/pnl/r_multiple/status）。交易可打多个 tag（如 `["sma_cross","趋势","Q1"]`）。
- `strategy_performance`：按 tag 聚合的胜率/期望/盈亏比。

`compute_strategy_metrics()` 是纯数学核心（**不依赖 DB，可单测**）：win/loss/expectancy/profit_factor。`StrategyTracker` 是 async 版，平仓后调 `recompute(tag)` 自动重算该 tag 聚合。

**why**：交易不记 = 无法复盘。tag 化让你能"看我所有用 sma_cross 策略的交易总体盈亏如何"，按 expectancy 排名策略，淘汰差的。`expectancy`（每笔期望盈亏）和 `profit_factor`（总盈利/总亏损）是量化最核心两个数。

**how**：
```python
from app.services.journal.analytics import compute_strategy_metrics
# entries 是 JournalEntry 列表（含 .pnl 和 .tags）
m = compute_strategy_metrics([e for e in entries if "sma_cross" in e.tags])
# m = {win_count, loss_count, win_rate, expectancy, profit_factor, avg_win, avg_loss, ...}

# async 持久化（在路由里，db 是 AsyncSession）:
from app.services.journal.analytics import StrategyTracker
await StrategyTracker(db).recompute("sma_cross")   # 平仓后触发
ranking = await StrategyTracker(db).compare_strategies()  # 按 expectancy 降序
```
**怎么验证**：`test_audit` 旁的逻辑；数学已验证（3 胜 1 负 1 保本 → win_rate .75, expectancy 112.5, profit_factor 5.5）。

---

## 6. 风险看板 `risk/service.py`

**what**：组合层面的风险视图，4 个能力——
- `compute_dashboard(positions)`：总市值、**行业集中度**、**VaR95/VaR99**（参数法，假设每仓 2% 日波动零相关）、总盈亏。
- `check_position_risk(...)`：加仓前模拟——把拟加仓位并入组合，对比"现在 vs 加仓后"的集中度/VaR 变化。
- `get_regime_adjusted_size(...)`：按 regime 调仓位（bull 全仓、choppy 0.75、bear 0.5）。
- `generate_alerts(positions)`：集中度>30% 警告/>50% 严重、单仓>20% 警告、组合回撤>10% 警告。

**why**：组合管理不能只看"涨多少"，要看风险。VaR 告诉你"极端情况下最多亏多少"；集中度告诉你"别把鸡蛋放一个篮子"；pre-trade 模拟让你加仓前看见影响。

**how**：
```python
from app.services.risk.service import compute_dashboard, check_position_risk, generate_alerts
positions = [{"symbol":"600519","shares":100,"cost_basis":1500,"current_price":1800,"sector":"白酒"}, ...]
d = compute_dashboard(positions)         # {total_value, max_sector_pct, portfolio_var_95, ...}
pt = check_position_risk(positions, "600519", 50, 1850)  # 加 50 股 1850 元的影响
alerts = generate_alerts(positions)     # [RiskAlert(...), ...]
```
纯数学，无 DB，全可单测。

---

## 7. 决策审计 `audit/`

**what**：`DecisionLog` 表记每次 agent 路由/LLM 调用——session_id、query 分类、用了哪些模型、token 数、**成本（美元）**、耗时、状态、错误类别。`DecisionLogger` 是 async 写入器。

**核心保证**：**所有方法捕获全部异常，审计写入永不阻塞/崩溃主流程**。agent 工作流绝不能因为"记日志失败"而崩。

**why**：用 LLM 烧钱，必须知道钱花哪了、哪类 query 多、成功率多少。`get_cost_summary(days)` 聚合最近 N 天成本/用量。永不抛异常的设计让它能安全地插到任何 agent 调用路径上。

**how**：
```python
from app.services.audit.logger import decision_logger
await decision_logger.log_decision(
    session_id="abc", query_classification="screening",
    models_used=["qwen"], tokens_input=100, tokens_output=50,
    estimated_cost_usd=0.001, duration_ms=250, status="success",
)
rows = await decision_logger.get_decisions(session_id="abc")
summary = await decision_logger.get_cost_summary(days=7)  # {total_requests, total_cost_usd, status_breakdown, ...}
```
**怎么验证**：`uv run python -m tests.test_audit`（永不抛异常在坏 DB 上 + temp-DB 读写 + 成本聚合）。

---

## 8. 回测 `backtesting/`（vectorbt 的纯 pandas 替代）

**what**：5 个文件——
- `strategies.py`：9 个纯 pandas 信号生成器（sma/ema/macd/rsi/bollinger/momentum/mean_reversion/breakout/volume_momentum）+ 12 个策略模板元数据。
- `engine.py`：纯 pandas 组合模拟器 `run_backtest()`——按 entries/exits 在收盘价上模拟满仓进出，含手续费，产出 total_return/sharpe/max_drawdown/win_rate/trade_count/profit_factor。
- `walk_forward.py`：滚动样本外——切窗口逐窗回测，聚合收益分布（均值/标准差/正收益占比）。
- `monte_carlo.py`：bootstrap 重采样交易收益 N 次，产出 total_return 的置信区间（p5/p25/中位/p75/p95）。
- `parser.py`：自然语言→策略（`parse_simple` 纯规则；`parse_with_llm` 可选接本平台 LLM，回退规则）。

**why（为什么不用 vectorbt）**：maverick 用 `vectorbtpro`（付费）。免费 `vectorbt` 在 Python 3.12 上因 `numba`/`llvmlite` 编译失败装不上（llvmlite 0.36 仅支持 Python<3.10）。所以我重写了**等价的最小引擎**——不算 vectorbt 的全量能力（参数寻优/ML），但回测/滚动外验/蒙特卡洛的核心算法都齐了，且零重依赖。

**how**：
```python
from app.services.backtesting.strategies import generate_signals
from app.services.backtesting.engine import run_backtest
from app.services.backtesting.walk_forward import walk_forward
from app.services.backtesting.monte_carlo import monte_carlo
from app.services.backtesting.parser import StrategyParser

# 1. 解析 NL 或直接选策略
cfg = StrategyParser().parse_simple("用 10 和 30 的 SMA 金叉")
# 2. 生成信号
entries, exits = generate_signals(cfg["strategy_type"], cfg["parameters"], df)
# 3. 回测
m = run_backtest(df, entries, exits, initial_capital=100_000, fees=0.001)
print(m.to_dict())  # {total_return, sharpe, max_drawdown, win_rate, ...}
# 4. 滚动外验 + 蒙特卡洛
wf = walk_forward(df, entries, exits, window=252, step=63)
mc = monte_carlo([t.return for t in trades], n_sims=1000)  # {p5, p95, median_return, ...}
```
**怎么验证**：`uv run python -m tests.test_backtesting`（14 项：信号生成+引擎+walk_forward+monte_carlo+parser）。

**为什么 `ensemble/regime_aware/online_learning` 抛 NotImplementedError**：这三个是高级形态，需要 ML/regime 检测/投票聚合，超出纯 pandas 范围。元数据保留，实现留接口。

---

## 9. 信号↔回测 `signals/backtest_adapter.py`

**what**：把第 2 节的**信号条件**转成第 8 节回测引擎要的 entries/exits，再回测。`backtest_signal_condition(cond, df)` 一行搞定。

**核心算法**：逐 bar 调 `evaluate_condition`，**跨 bar 传 previous_state**（crosses_* 有状态必须），对 triggered 序列做边沿检测（本 bar 触发且上 bar 没触发 = entry）。

**why**：打通"告警设计↔回测"。你设计一个告警"RSI 上穿 50"，先**历史复盘**看这条规则在过去赚不赚钱、回撤多大，再决定要不要部署为实时告警。否则盲目上线可能是个亏钱规则。

**how**：
```python
from app.services.signals.backtest_adapter import backtest_signal_condition
cond = {"indicator":"rsi","operator":"crosses_above","threshold":50,"period":14}
m = backtest_signal_condition(cond, df)  # BacktestMetrics
print(m.total_return, m.max_drawdown, m.win_rate)
```

---

## 怎么跑全部测试

```bash
cd backend
uv run pytest -q          # 6 个测试文件全过
# 或单独跑：
uv run python -m tests.test_indicators
uv run python -m tests.test_backtesting
uv run python -m tests.test_audit
uv run python -m tests.test_authz
uv run python -m tests.test_sandbox
```

## 后续集成（移植只到库层，未接路由）

这些模块现在是**可调用的库 + 测试**，还没挂到 FastAPI 路由。后续要让它在前端可用，需各自加一个 router（如 `app/api/v1/journal.py`、`risk.py`、`backtest_strategies.py`），仿现有 `portfolios.py` 模式。这是下一步工作，不在本次移植范围。

## 致谢

所有移植代码源自 [wshobson/maverick-mcp](https://github.com/wshobson/maverick-mcp)（MIT License, Copyright (c) 2024），在每个移植文件头署名。研读笔记见 `.ai/research/maverick-mcp-study.md`。

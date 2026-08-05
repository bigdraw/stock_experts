"""FactBook——辩论前的共享事实基础（两阶段辩论·阶段1：数据准备）。

阶段1是纯代码（非 LLM agent）：拉取全量数据 + 客观校验，输出结构化 FactBook，
作为阶段2所有投资大师 agent 的**统一事实基础**。各 agent 在此基础上评估，
仍可按自己 system_prompt 设定调用工具获取关注的其他信息。

解决的历史问题：
1. 数据不全面：orchestrator 只注入 latest（单期）+ valuation + growth，丢掉 trend/dividends/K线。
2. 无宏观/行业视角：补充行业动态 + 宏观政策 + 沪深300市场状态。
3. 无数据校验：_validate 检查财报时效性/K线缺口/字段完整性/逻辑一致性。
4. agent 各自盲评：所有 agent 看到同一份 FactBook。
5. 时间窗口不一致：K线取 5 年（与价值分析的 5 年年报 CAGR + 20 期历史对齐）。

复用原则：不重复造轮子——
- value_analysis.analyze（6维 + trend20期 + dividends）
- ensure_full_daily_quotes（全量日K，供周/月线 resample + 趋势统计）
- RegimeDetector.classify（沪深300 regime）
- web_search（行业 + 宏观，tavily 优先 DuckDuckGo 备选）

采集器全部 try/except 降级：单点数据源失败不阻断辩论，只在 <data_warnings> 标注。
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import date, datetime, timedelta
from typing import Any

import httpx
import pandas as pd
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.stock import DailyQuote, FinancialReport, Stock
from app.services.data.akshare_provider import AkShareProvider
from app.services.data.cache import (
    ensure_daily_quotes,
    ensure_financial_reports,
    ensure_full_daily_quotes,
)
from app.services.data.value_analysis import analyze
from app.services.signals.regime import RegimeDetector

logger = logging.getLogger(__name__)

# 沪深300指数代码（akshare index 口径）
_HS300_INDEX = "000300"
# K线时间窗口与价值分析对齐：5年
_KLINE_YEARS = 5
# 财报过期阈值：按 report_date（报告期末日，非披露日）算，Q1 期末 3/31 到 8 月初约
# 126 天。Q1 是季报披露后到 H1 披露前的正常"最新"，120 天会误报。调到 150 天，
# Q1 要到 8 月底才告警（届时 H1 通常已披露），仍能抓到真过期（半年以上无新报）。
_REPORT_STALE_DAYS = 150


class FactBook:
    """辩论前的共享事实基础——全量数据 + 客观校验结果。

    所有 agent 共享同一份 FactBook，避免"各自盲评"。
    """

    def __init__(self, provider: AkShareProvider | None = None) -> None:
        self.provider = provider or AkShareProvider()

    async def collect(self, stock_code: str, db: AsyncSession) -> dict[str, Any]:
        """收集全量数据（复用现有端点逻辑）+ 客观校验。

        返回结构化 FactBook dict。所有采集器独立降级——失败项置空 +
        在 validation.warnings 记录，不抛异常。
        """
        stock = await db.get(Stock, stock_code)
        name = stock.name if stock else stock_code
        industry_fb = stock.industry or stock.sector if stock else None
        facts: dict[str, Any] = {
            "stock_code": stock_code,
            "stock_name": name,
            "collected_at": datetime.now().isoformat(timespec="seconds"),
        }

        # 1. 价值分析全量（含 trend 20期 + dividends）——复用 value_analysis，失败重试+快照兜底
        facts["value_analysis"] = await self._collect_value_analysis(stock_code, db)

        # 2. K线趋势（5年，与价值分析时间窗口对齐）——复用 ensure_full_daily_quotes，失败重试+短窗口兜底
        facts["kline"] = await self._collect_kline(stock_code, db)

        # 3. 行业动态 + 宏观政策（web_search，失败重试；行业空则用公司行业字段兜底）
        facts["industry"] = await self._collect_industry(name, industry_fb)
        facts["macro"] = await self._collect_macro()

        # 4. 市场状态（沪深300 regime）——沪深300不可用则用个股自身趋势代理
        facts["market_regime"] = await self._collect_regime(stock_code, db)

        # 5. 客观校验（完整性/时效性/逻辑一致性）
        facts["validation"] = self._validate(facts)

        return facts

    # ─────────────────────────── 采集器 ───────────────────────────

    async def _collect_value_analysis(self, code: str, db: AsyncSession) -> dict[str, Any]:
        """复用 value_analysis.analyze：6维 + trend20期 + dividends + growth CAGR。

        远端/网络偶发失败 → 重试 3 次；仍失败则取 Latest 快照 + 最近一期周期财报
        的最小指标兜底（至少有估值/ROE/EPS），不让 value_analysis 整块缺失。
        """
        last_err = None
        for attempt in range(3):
            try:
                await ensure_financial_reports(db, code, provider=self.provider)
                await db.commit()
                va = await analyze(db, code, provider=self.provider)
                if "error" not in va:
                    return va
                last_err = va["error"]
                logger.warning(f"FactBook: value_analysis attempt {attempt + 1}/3 error: {last_err}")
            except Exception as e:
                last_err = e
                logger.warning(f"FactBook: value_analysis attempt {attempt + 1}/3 failed: {e!r}")
        logger.warning(f"FactBook: value_analysis fallback to minimal snapshot for {code}: {last_err!r}")
        return await self._value_analysis_fallback(code, db)

    async def _value_analysis_fallback(self, code: str, db: AsyncSession) -> dict[str, Any]:
        """兜底：analyze 全失败时，从 FinancialReport 取 Latest 快照 + 最近周期财报。"""
        snap = (await db.execute(
            select(FinancialReport).where(
                FinancialReport.stock_code == code, FinancialReport.report_type == "Latest"
            ).order_by(FinancialReport.report_date.desc()).limit(1)
        )).scalar_one_or_none()
        periodic = (await db.execute(
            select(FinancialReport).where(
                FinancialReport.stock_code == code, FinancialReport.report_type != "Latest"
            ).order_by(FinancialReport.report_date.desc()).limit(1)
        )).scalar_one_or_none()
        latest, valuation = {}, {}
        if periodic:
            latest = {
                "report_date": str(periodic.report_date) if periodic.report_date else None,
                "roe": periodic.roe, "eps": periodic.eps, "bps": periodic.bps,
                "revenue": periodic.revenue, "net_profit": periodic.net_profit,
                "debt_ratio": periodic.debt_ratio,
            }
        if snap:
            valuation = {"pe": snap.per, "pb": snap.pb, "price": snap.price}
        if not latest and not valuation:
            return {"_error": f"value_analysis 全部失败且无快照可兜底: {code}"}
        return {"latest": latest, "valuation": valuation, "_fallback": "minimal_snapshot"}

    async def _collect_kline(self, code: str, db: AsyncSession) -> dict[str, Any]:
        """取 K线，提取趋势摘要。时间窗口与价值分析一致：5年。

        层1：全量5年日K，重试3次；层2兜底：120日短窗口（akshare 近期数据更稳，
        摘要自动对短数据返回 None 字段）。两层都失败才 _error。
        """
        last_err = None
        for attempt in range(3):
            try:
                await ensure_full_daily_quotes(db, code, provider=self.provider)
                await db.flush()
                summary = await self._kline_summarize(code, db)
                if "_error" not in summary:
                    return summary
                last_err = summary["_error"]
            except Exception as e:
                last_err = e
                logger.warning(f"FactBook: kline full attempt {attempt + 1}/3 failed: {e!r}")
        logger.warning(f"FactBook: kline fallback to 120d window for {code}: {last_err!r}")
        try:
            await ensure_daily_quotes(db, code, days=120, provider=self.provider)
            await db.flush()
            summary = await self._kline_summarize(code, db)
            if "_error" not in summary:
                summary["_fallback"] = "120d_window"
                return summary
        except Exception as e:
            logger.warning(f"FactBook: kline 120d fallback failed: {e!r}")
        return {"_error": f"kline 全量+短窗口均失败: {last_err!r}"}

    async def _kline_summarize(self, code: str, db: AsyncSession) -> dict[str, Any]:
        """从 DB 读日K → 趋势摘要（日/周/月 + 缺口）。短数据自动返回 None 字段。"""
        rows = (
            await db.execute(
                select(DailyQuote.date, DailyQuote.close, DailyQuote.volume)
                .where(DailyQuote.stock_code == code)
                .order_by(DailyQuote.date.asc())
            )
        ).all()
        if not rows:
            return {"_error": "无日K数据"}
        df = pd.DataFrame(rows, columns=["date", "close", "volume"]).dropna(subset=["close"])
        if df.empty:
            return {"_error": "无有效收盘价"}
        df["date"] = pd.to_datetime(df["date"])

        daily_summary = self._kline_daily_summary(df)
        weekly_summary = self._kline_period_summary(df, "W", {"近13周": 13, "近26周": 26, "近52周": 52})
        monthly_summary = self._kline_period_summary(
            df, "ME", {"近6月": 6, "近12月": 12, "近60月(5年)": 60}
        )
        # 缺口检查：最近30个交易日缺失天数
        recent_30 = df.sort_values("date").tail(30)
        gaps = 0
        if len(recent_30) > 1:
            diffs = recent_30["date"].diff().dt.days
            gaps = int(((diffs > 4) & (diffs <= 7)).sum() + (diffs > 7).sum())
        return {
            "daily": {"summary": daily_summary, "missing_days_30d": gaps},
            "weekly": {"summary": weekly_summary},
            "monthly": {"summary": monthly_summary},
        }

    def _kline_daily_summary(self, df: pd.DataFrame) -> dict[str, Any]:
        """日K趋势摘要：多周期涨跌 + 年化 + 回撤 + 高低点 + 量比。"""
        close = df["close"].astype(float)
        last = float(close.iloc[-1])
        vol = df["volume"].astype(float)

        def _change(n: int) -> float | None:
            if len(close) <= n:
                return None
            base = float(close.iloc[-n - 1])
            return round((last / base - 1) * 100, 2) if base else None

        # 5年最大回撤
        window = close.tail(_KLINE_YEARS * 252 + 10) if len(close) > _KLINE_YEARS * 252 else close
        cummax = window.cummax()
        drawdown = (window / cummax - 1) * 100
        max_dd = round(float(drawdown.min()), 2) if not drawdown.empty else None

        # 5年年化收益
        change_5y = _change(_KLINE_YEARS * 252)
        ann_5y = None
        if change_5y is not None:
            ann_5y = round(((1 + change_5y / 100) ** (1 / _KLINE_YEARS) - 1) * 100, 2)

        # 近5年高低点
        w5 = close.tail(_KLINE_YEARS * 252 + 10)
        high5 = round(float(w5.max()), 4) if not w5.empty else None
        low5 = round(float(w5.min()), 4) if not w5.empty else None
        near_high = bool(high5 and last >= high5 * 0.97)
        near_low = bool(low5 and last <= low5 * 1.03)

        # 量比：近20日均量 / 5年均量
        v20 = float(vol.tail(20).mean()) if len(vol) >= 20 else None
        v5y = float(vol.tail(_KLINE_YEARS * 252).mean()) if len(vol) >= 60 else None
        vol_ratio = round(v20 / v5y, 2) if (v20 and v5y) else None

        return {
            "last_close": last,
            "change_1m": _change(22),
            "change_3m": _change(66),
            "change_6m": _change(132),
            "change_1y": _change(252),
            "change_5y": change_5y,
            "annualized_5y": ann_5y,
            "max_drawdown_5y_pct": max_dd,
            "high_5y": high5,
            "low_5y": low5,
            "near_5y_high": near_high,
            "near_5y_low": near_low,
            "volume_ratio_20d_vs_5y": vol_ratio,
        }

    def _kline_period_summary(self, df: pd.DataFrame, freq: str, lookbacks: dict[str, int]) -> dict[str, float | None]:
        """周/月K趋势：各回看周期涨跌幅（%）"""
        try:
            resampled = df.set_index("date")["close"].astype(float).resample(freq).last().dropna()
        except Exception:
            return {k: None for k in lookbacks}
        last = float(resampled.iloc[-1]) if not resampled.empty else None
        out: dict[str, float | None] = {}
        for label, n in lookbacks.items():
            if last and len(resampled) > n:
                base = float(resampled.iloc[-n - 1])
                out[label] = round((last / base - 1) * 100, 2) if base else None
            else:
                out[label] = None
        return out

    async def _collect_industry(self, stock_name: str, industry_fallback: str | None = None) -> str:
        """web_search 搜行业动态（竞争格局/行业增速）。搜索为空时用公司行业字段兜底。"""
        res = await self._web_search(f"{stock_name} 行业分析 竞争格局 行业增速 2026")
        if res:
            return res
        if industry_fallback:
            return f"（联网搜索为空，兜底取公司行业字段）行业：{industry_fallback}"
        return ""

    async def _collect_macro(self) -> str:
        """web_search 搜宏观政策（货币政策/利率/CPI）。"""
        return await self._web_search("中国 A股 宏观经济 货币政策 利率 CPI 最新 2026")

    async def _collect_regime(self, code: str | None = None, db: AsyncSession | None = None) -> dict[str, Any]:
        """沪深300市场状态检测（bull/bear/choppy/transitional）。

        沪深300 拉不到（akshare 指数端偶发断连）→ 兜底用个股自身 60 日收盘做
        趋势代理（RegimeDetector 对任意价格序列都适用），标注 _fallback。
        """
        try:
            quotes = await self._fetch_index_quotes(_HS300_INDEX, days=70)
            if len(quotes) < 51:
                raise ValueError(f"沪深300样本不足({len(quotes)}), 需≥51")
            prices = pd.Series([float(q) for q in quotes], name="close")
            ret = prices.pct_change().dropna()
            vol_proxy = float(ret.tail(20).std() * (252 ** 0.5) * 100) if len(ret) >= 20 else 20.0
            detector = RegimeDetector()
            res = detector.classify(prices, vix_level=vol_proxy, breadth_ratio=None)
            res["volatility_proxy"] = round(vol_proxy, 2)
            return res
        except Exception as e:
            logger.warning(f"FactBook: regime 沪深300 failed: {e!r}, try stock-proxy fallback")
            # 兜底：用个股自身 60 日收盘做趋势代理
            if code and db:
                try:
                    rows = (await db.execute(
                        select(DailyQuote.close).where(DailyQuote.stock_code == code)
                        .order_by(DailyQuote.date.desc()).limit(60)
                    )).scalars().all()
                    if len(rows) >= 51:
                        prices = pd.Series([float(r) for r in rows][::-1], name="close")
                        ret = prices.pct_change().dropna()
                        vol_proxy = float(ret.tail(20).std() * (252 ** 0.5) * 100) if len(ret) >= 20 else 20.0
                        res = RegimeDetector().classify(prices, vix_level=vol_proxy, breadth_ratio=None)
                        res["volatility_proxy"] = round(vol_proxy, 2)
                        res["_fallback"] = "stock_proxy"
                        res["_note"] = f"沪深300不可用({e!r}), 用个股自身60日趋势代理"
                        return res
                except Exception as e2:
                    logger.warning(f"FactBook: regime stock-proxy fallback failed: {e2!r}")
            return {"_error": f"沪深300+个股代理均失败: {e!r}"}

    async def _fetch_index_quotes(self, index_code: str, days: int) -> list[float]:
        """拉取指数近 N 日收盘（akshare index_zh_a_hist）。

        akshare 指数端点偶发 RemoteDisconnected（远端掐连接），重试最多 3 次，
        并复用 akshare_provider 的 _bypass_proxy 绕过代理（与个股数据拉取一致）。
        """
        import akshare as ak

        from app.services.data.akshare_provider import _bypass_proxy, _restore_proxy

        end = date.today().strftime("%Y%m%d")
        start = (date.today() - timedelta(days=int(days * 1.8))).strftime("%Y%m%d")
        df = None
        for attempt in range(3):
            original = _bypass_proxy()
            try:
                df = await asyncio.to_thread(
                    ak.index_zh_a_hist, symbol=index_code, period="daily",
                    start_date=start, end_date=end,
                )
                if df is not None and not df.empty:
                    break
            except Exception as e:
                logger.warning(f"FactBook: index fetch attempt {attempt + 1}/3 failed: {e!r}")
            finally:
                _restore_proxy(original)
        if df is None or df.empty:
            return []
        col = "收盘" if "收盘" in df.columns else df.columns[-1]
        return df[col].astype(float).tolist()

    async def _web_search(self, query: str) -> str:
        """调 web-search 逻辑（tavily 优先，DuckDuckGo 备选）。

        tavily/duckduckgo 经 httpx，远端偶发 RemoteDisconnected → 重试最多 2 次。
        """
        tavily_key = os.environ.get("TAVILY_API_KEY")
        if tavily_key:
            for attempt in range(2):
                try:
                    async with httpx.AsyncClient(timeout=15) as client:
                        resp = await client.post(
                            "https://api.tavily.com/search",
                            json={"api_key": tavily_key, "query": query, "max_results": 3, "include_answer": True},
                        )
                        if resp.status_code == 200:
                            data = resp.json()
                            # 每条结果截到 600 字（[:150] 会句中断裂、信息错乱）；
                            # answer + 3 条 × 600 字 ≈ 2k 字，注入 FactBook 供 agent 引用，不致过大。
                            return (data.get("answer", "") or "") + "\n" + "\n".join(
                                f"- {r.get('title', '')}: {r.get('content', '')[:600]}" for r in data.get("results", [])
                            )
                except Exception as e:
                    logger.warning(f"tavily search attempt {attempt + 1}/2 failed: {e!r}")

        # DuckDuckGo fallback
        for attempt in range(2):
            try:
                async with httpx.AsyncClient(timeout=10) as client:
                    resp = await client.get(
                        "https://api.duckduckgo.com/",
                        params={"q": query, "format": "json", "no_html": 1, "skip_disambig": 1},
                    )
                if resp.status_code == 200:
                    data = resp.json()
                    results = []
                    if data.get("AbstractText"):
                        results.append(data["AbstractText"][:600])
                    for topic in (data.get("RelatedTopics") or [])[:3]:
                        if isinstance(topic, dict) and topic.get("Text"):
                            results.append(topic["Text"][:400])
                    if results:
                        return "\n".join(results)
            except Exception as e:
                logger.warning(f"duckduckgo search attempt {attempt + 1}/2 failed: {e!r}")
        return ""

    # ─────────────────────────── 客观校验 ───────────────────────────

    def _validate(self, facts: dict[str, Any]) -> dict[str, Any]:
        """检查数据完整性 + 时效性 + 逻辑一致性（客观，不带投资观点）。"""
        warnings: list[str] = []
        errors: list[str] = []

        va = facts.get("value_analysis", {}) or {}
        if va.get("_error"):
            errors.append(f"价值分析失败: {va['_error']}")
        else:
            latest = va.get("latest", {}) or {}
            # 财报时效性
            report_date = latest.get("report_date")
            if report_date:
                try:
                    rd = self._parse_date(report_date)
                    age = (datetime.now().date() - rd).days
                    if age > _REPORT_STALE_DAYS:
                        warnings.append(f"最新财报 {report_date} 距今 {age} 天，可能已过期")
                except Exception:
                    warnings.append(f"财报日期不可解析: {report_date}")
            # 完整性
            if latest.get("roe") is None:
                warnings.append("ROE 缺失")
            if latest.get("eps") is None:
                warnings.append("EPS 缺失")
            # 逻辑一致性：ROE vs ROIC——高 ROE 但低/负 ROIC 提示杠杆撑起的虚假回报
            roe = latest.get("roe")
            roic = latest.get("roic")
            if roe is not None and roic is not None and roe > 0 and roic < 0:
                warnings.append(f"ROE={roe} 为正但 ROIC={roic} 为负，回报可能依赖高杠杆而非经营")
            # 盈利质量：OCF/净利润 <0.8 警惕
            eq = latest.get("earnings_quality")
            if eq is not None and eq < 0.8:
                warnings.append(f"盈利质量 OCF/净利润={eq:.2f} <0.8，利润现金支撑偏弱")

        kl = facts.get("kline", {}) or {}
        if kl.get("_error"):
            warnings.append(f"K线数据缺失: {kl['_error']}")
        else:
            missing = (kl.get("daily", {}) or {}).get("missing_days_30d", 0)
            if missing and missing > 5:
                warnings.append(f"近30日K线有 {missing} 个缺口")
            dd = (kl.get("daily", {}) or {}).get("summary", {}) or {}
            if dd.get("max_drawdown_5y_pct") is not None and dd["max_drawdown_5y_pct"] < -50:
                warnings.append(f"5年最大回撤 {dd['max_drawdown_5y_pct']}%，波动剧烈")

        mr = facts.get("market_regime", {}) or {}
        if mr.get("_error"):
            warnings.append(f"市场状态检测失败: {mr['_error']}")

        if not facts.get("industry"):
            warnings.append("行业动态搜索为空")
        if not facts.get("macro"):
            warnings.append("宏观政策搜索为空")

        status = "error" if errors else ("warn" if warnings else "ok")
        return {"status": status, "warnings": warnings, "errors": errors}

    @staticmethod
    def _parse_date(s: str) -> date:
        s = str(s)
        if len(s) == 8 and "-" not in s:
            return date(int(s[:4]), int(s[4:6]), int(s[6:8]))
        return datetime.fromisoformat(s).date()

    # ─────────────────────────── 格式化（LLM 友好） ───────────────────────────

    def format(self, fb: dict[str, Any]) -> str:
        """将 FactBook 格式化为 LLM 友好的分节文本（不截断，按维度分节）。

        这是所有 agent 看到的**统一事实基础**。校验结果放最前面，
        让 agent 知道数据质量后再引用数据。
        """
        sections: list[str] = []

        # 校验结果放最前面
        val = fb.get("validation", {}) or {}
        if val.get("warnings") or val.get("errors"):
            lines = []
            if val.get("errors"):
                lines.append("错误（数据不可用，谨慎引用）:")
                lines += [f"  - {e}" for e in val["errors"]]
            if val.get("warnings"):
                lines.append("警告（数据可能有质量风险）:")
                lines += [f"  - {w}" for w in val["warnings"]]
            sections.append("<data_warnings>\n" + "\n".join(lines) + "\n</data_warnings>")
        else:
            sections.append("<data_warnings>无（数据完整且新鲜）</data_warnings>")

        # 标的概要
        sections.append(
            f"<target>\n标的: {fb.get('stock_name', '')}（{fb.get('stock_code', '')}）"
            f"\n采集时间: {fb.get('collected_at', '')}\n</target>"
        )

        # 价值分析全量（含 trend 序列 + dividends）
        va = fb.get("value_analysis", {}) or {}
        if not va.get("_error"):
            sections.append(f"<value_analysis>\n{json.dumps(va, ensure_ascii=False, default=str)}\n</value_analysis>")

        # K线摘要（不注入全量数千根，只注入统计）
        kl = fb.get("kline", {}) or {}
        if not kl.get("_error"):
            sections.append(f"<kline_summary>\n{json.dumps(kl, ensure_ascii=False, default=str)}\n</kline_summary>")

        # 行业动态
        if fb.get("industry"):
            sections.append(f"<industry>\n{fb['industry']}\n</industry>")

        # 宏观政策
        if fb.get("macro"):
            sections.append(f"<macro>\n{fb['macro']}\n</macro>")

        # 市场状态
        mr = fb.get("market_regime", {}) or {}
        if not mr.get("_error"):
            sections.append(f"<market_regime>\n{json.dumps(mr, ensure_ascii=False, default=str)}\n</market_regime>")

        return "\n\n".join(sections)

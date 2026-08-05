#!/usr/bin/env python3
"""数据质量自迭代脚本：随机抓取 → 代码级检查 → LLM 核验 → 输出报告。

用法：cd backend && uv run python scripts/data_quality_loop.py [--n 5] [--no-llm]

每轮输出 data_quality_report.md（追加），开发者读 → 修 bug → 重跑 → 确认 issue 数下降。
"""

from __future__ import annotations

import asyncio
import json
import logging
import random
import sys
from datetime import datetime
from pathlib import Path

_BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_BACKEND))

from sqlalchemy import select  # noqa: E402

from app.database import async_session_factory, init_db  # noqa: E402
from app.models.stock import Stock  # noqa: E402
from app.services.debate.factbook import FactBook  # noqa: E402
from app.services.debate.orchestrator import DebateOrchestrator  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

REPORT_FILE = _BACKEND / "data_quality_report.md"


# ─────────────────── 代码级自动检查 ───────────────────

def _is_complex(v) -> bool:
    return isinstance(v, complex)


def _check_numeric(field: str, val, lo: float, hi: float, issues: list, stock: str):
    if val is None:
        return
    if _is_complex(val):
        issues.append({"stock": stock, "field": field, "value": str(val),
                       "problem": "复数（CAGR/Graham bug）", "severity": "high",
                       "fix": "基期或终期 ≤0 时应 return None"})
        return
    if isinstance(val, str):
        return
    if val < lo or val > hi:
        issues.append({"stock": stock, "field": field, "value": val,
                       "problem": f"超出合理范围 [{lo}, {hi}]", "severity": "high" if abs(val) > 10 * hi else "medium"})


def code_level_check(raw: dict, stock_code: str, stock_name: str) -> list[dict]:
    """对 raw FactBook data 跑硬编码断言，返回 issue list。"""
    issues: list[dict] = []
    label = f"{stock_name}({stock_code})"
    va = raw.get("value_analysis", {})
    if "_error" in va:
        issues.append({"stock": label, "field": "value_analysis", "value": va["_error"],
                       "problem": "价值分析整体失败", "severity": "high"})
        return issues

    latest = va.get("latest", {})
    val = va.get("valuation", {})
    growth = va.get("growth", {})
    kline = raw.get("kline", {})
    regime = raw.get("market_regime", {})

    # 类型检查：复数
    for field, v in [("pe", val.get("pe")), ("pb", val.get("pb")), ("graham_number", val.get("graham_number")),
                     ("cagr_3y_revenue", growth.get("revenue", {}).get("cagr_3y")),
                     ("cagr_5y_net_profit", growth.get("net_profit", {}).get("cagr_5y"))]:
        if _is_complex(v):
            issues.append({"stock": label, "field": field, "value": str(v),
                           "problem": "复数（代码 bug）", "severity": "high",
                           "fix": "负值开根号 → 跳过/return None"})

    # 数值合理性
    _check_numeric("pe", val.get("pe"), -200, 2000, issues, label)
    _check_numeric("pb", val.get("pb"), 0, 100, issues, label)
    _check_numeric("roe", latest.get("roe"), -1, 1, issues, label)
    _check_numeric("dividend_yield", val.get("dividend_yield"), -0.01, 0.5, issues, label)
    _check_numeric("fcf_yield", val.get("fcf_yield"), -0.5, 1, issues, label)

    # 完整性
    for f in ["roe", "eps", "revenue"]:
        if latest.get(f) is None:
            issues.append({"stock": label, "field": f"latest.{f}", "value": None,
                           "problem": f"{f} 缺失", "severity": "medium"})
    for f in ["pe", "pb"]:
        if val.get(f) is None:
            issues.append({"stock": label, "field": f"valuation.{f}", "value": None,
                           "problem": f"{f} 缺失", "severity": "medium"})

    # 分红合理性
    divs = va.get("dividends", [])
    price = val.get("price")
    for d in divs[:3]:
        dps = d.get("dividend_per_share")
        if dps and price and dps > price:
            issues.append({"stock": label, "field": "dividend_per_share", "value": dps,
                           "problem": f"dps={dps} > price={price}（可能未/10）", "severity": "high"})
    if divs and not any(d.get("dividend_per_share") for d in divs):
        issues.append({"stock": label, "field": "dividends", "value": None,
                       "problem": "有分红记录但 dps 全空", "severity": "medium"})

    # K线
    if "_error" in kline:
        issues.append({"stock": label, "field": "kline", "value": kline["_error"],
                       "problem": "K线全量+短窗口均失败", "severity": "high"})
    else:
        ds = kline.get("daily", {}).get("summary", {})
        if not ds.get("last_close"):
            issues.append({"stock": label, "field": "kline.last_close", "value": None,
                           "problem": "last_close 缺失", "severity": "high"})
        dd = ds.get("max_drawdown_5y_pct")
        if dd is not None and (dd > 0 or dd < -90):
            issues.append({"stock": label, "field": "kline.max_drawdown", "value": dd,
                           "problem": f"max_drawdown={dd}% 不合理（>0 或 <-90%）", "severity": "medium"})

    # regime
    if "_error" in regime:
        issues.append({"stock": label, "field": "market_regime", "value": regime["_error"],
                       "problem": "沪深300+个股代理均失败", "severity": "medium"})
    elif regime.get("regime") not in ("bull", "bear", "choppy", "transitional"):
        issues.append({"stock": label, "field": "market_regime", "value": regime.get("regime"),
                       "problem": "regime 值异常", "severity": "low"})

    # 季报 ROE 提示
    roe = latest.get("roe")
    rd = latest.get("report_date", "")
    if roe is not None and abs(roe) < 0.02 and rd and not str(rd).endswith("12-31"):
        issues.append({"stock": label, "field": "latest.roe", "value": roe,
                       "problem": f"ROE={roe:.4f} 偏低可能是季报值（{rd}），非年化", "severity": "low"})

    return issues


# ─────────────────── LLM 核验 ───────────────────

async def llm_validate(raw: dict, digest: str, stock_code: str, stock_name: str, code_issues: list) -> dict | None:
    """LLM 独立核验数据质量（财报审计视角，enable_thinking=True 不截断）。

    同时审计：①原始采集数据的正确性 ②事实 agent digest 是否忠实反映原始数据。
    从注册会计师/财务分析师角度深度核验：数值合理性、报表勾稽关系、
    时间序列一致性、计算正确性、数据完整性。不是走过场。
    """
    try:
        from app.services.llm.manager import llm_manager
        from app.services.llm.provider import LLMMessage
        llm = llm_manager.get()
    except Exception as e:
        logger.warning(f"llm_validate: llm_manager.get() failed: {e!r}")
        return None

    system = (
        "你是一位**注册会计师（CPA）+ 财务分析师**，正在对一只 A 股股票的自动采集数据做**审计级核验**。\n\n"
        "你的职责不是做投资分析，而是**检验数据本身是否正确、完整、自洽**。你需要像一个审计师一样，"
        "逐项核对数字，质疑异常，验证勾稽关系。\n\n"
        "## 核验维度\n\n"
        "### 1. 数值合理性\n"
        "- PE/PB/PS 是否在合理区间（PE 通常 3-200，PB 0.1-30；极端值需标注）\n"
        "- ROE/ROIC 是否为小数（0-0.5 正常，>1 或 <0 需质疑）\n"
        "- 股息率 0-8% 正常，>15% 可能分红未归一化\n"
        "- EPS/BPS 与市值/股价是否匹配\n"
        "- 毛利率/净利率是否合理（制造业 5-30%，金融业特殊）\n"
        "- 资产负债率 0-1（金融股可 >0.9）\n\n"
        "### 2. 报表勾稽关系\n"
        "- 资产负债表：资产 = 负债 + 所有者权益（检查是否自洽）\n"
        "- 利润表：营收 - 成本 - 费用 = 净利润（毛利率 × 营收 ≈ 毛利）\n"
        "- 现金流量表：OCF = 净利润 + 折旧 ± 营运资本变动；FCF = OCF - Capex\n"
        "- ROE = 净利润 / 所有者权益；ROIC = NOPAT / 投入资本\n"
        "- Graham number = sqrt(22.5 × EPS × BVPS)（验证计算）\n\n"
        "### 3. 时间序列一致性\n"
        "- trend 里各期 ROE/EPS/营收是否连续（非断崖式跳变）\n"
        "- 年报 = Q1+Q2+Q3+Q4 累计（单季值不应 > 年报值）\n"
        "- CAGR 是否因基数效应失真（疫情年/重组年导致的虚假高增长）\n"
        "- 季报值 vs 年报值：Q1 ROE 通常为年报的 1/4，不应直接当年化用\n\n"
        "### 4. 数据完整性\n"
        "- 关键指标是否缺失（ROE/EPS/revenue/OCF/FCF）\n"
        "- trend 序列是否被截断（应有 20 期）\n"
        "- 分红数据是否有 dps 值（非空记录但数值为空）\n"
        "- K线是否有缺口（最近 30 日缺失天数）\n\n"
        "### 5. 明显错误\n"
        "- 复数值（CAGR/Graham sqrt 负数）\n"
        "- None 值出现在应有值的字段\n"
        "- 单位错误（万元 vs 元、每10股 vs 每股）\n"
        "- 类型错误（字符串混入数值字段）\n\n"
        "## 输出要求\n\n"
        "输出 JSON（思考完毕后给出，思考过程不需要输出）：\n"
        "```json\n"
        "{\"issues\": [{\"field\": \"字段名\", \"value\": \"当前值\", "
        "\"problem\": \"问题描述+根因分析\", \"severity\": \"high/medium/low\", "
        "\"fix_suggestion\": \"修复建议\"}], \"trust\": \"high/medium/low\", "
        "\"summary\": \"一句话总评\"}\n"
        "```\n\n"
        "severity 标准：\n"
        "- high: 数据错误会导致投资判断方向性错误（如分红未/10、PE 算错、复数）\n"
        "- medium: 数据有疑问但不一定是 bug（如 CAGR 基数效应、季报未年化）\n"
        "- low: 信息性提示（如数据缺失但不影响核心判断）\n\n"
        "trust 标准：\n"
        "- high: 数据完整自洽，可直接用于投资分析\n"
        "- medium: 有疑问但不致命，需人工复核\n"
        "- low: 有严重数据错误，不可直接使用"
    )
    user = (
        f"标的：{stock_name}({stock_code})\n\n"
        f"代码级自动检查结果（仅供参考，你需要独立判断，不要盲信）：\n"
        f"{json.dumps(code_issues, ensure_ascii=False, default=str)}\n\n"
        f"--- 原始采集数据（JSON）---\n"
        f"{json.dumps(raw, ensure_ascii=False, default=str)}\n\n"
        f"--- 事实 agent 整理的 digest（投资 agent 实际看到的）---\n"
        f"{digest}\n\n"
        f"请分别审计：①原始数据的正确性 ②事实 agent digest 是否忠实反映原始数据（有无遗漏/篡改/幻觉）"
    )

    try:
        # 用 chat_stream（非 chat）——enable_thinking=True 时思考很长，
        # 非流式 chat 会 ReadTimeout（httpx 300s）；流式 token 持续回流不超时。
        text = ""
        async for chunk in llm.chat_stream([
            LLMMessage(role="system", content=system),
            LLMMessage(role="user", content=user),
        ], max_tokens=None, enable_thinking=True):
            if chunk.content:
                text += chunk.content
        if not text:
            logger.warning("llm_validate: LLM content 为空（thinking 吃满？）")
            return None
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            result = json.loads(text[start:end + 1])
            return result
        else:
            logger.warning(f"llm_validate: LLM 返回无 JSON, content[:300]={text[:300]}")
    except Exception as e:
        logger.warning(f"llm_validate: llm.chat() failed for {stock_code}: {e!r}")
    return None


# ─────────────────── 主循环 ───────────────────

async def run_one_round(n: int = 5, use_llm: bool = True) -> list[dict]:
    """一轮：随机抓取 → 代码级检查 → LLM 核验 → 返回所有 issues。"""
    await init_db()

    # 初始化 LLM（脚本不走 FastAPI lifespan，需手动 reload）
    llm_ready = False
    if use_llm:
        try:
            from app.services.llm.manager import llm_manager
            async with async_session_factory() as db:
                await llm_manager.reload(db)
            llm_ready = True
            print(f"LLM 初始化成功: {llm_manager.list_providers()}")
        except Exception as e:
            print(f"⚠️ LLM 初始化失败: {e!r}，将跳过 LLM 核验")

    all_issues: list[dict] = []

    async with async_session_factory() as db:
        rows = (await db.execute(select(Stock).where(Stock.is_active == True))).scalars().all()  # noqa: E712
        if not rows:
            print("DB 无 active 股票")
            return []
        samples = random.sample(rows, min(n, len(rows)))

    for stock in samples:
        code, name = stock.code, stock.name
        print(f"\n{'='*60}\n采集 {name}({code})...")
        raw = None
        try:
            async with async_session_factory() as db:
                fb = FactBook()
                async for ev in fb.collect_streaming(code, db):
                    if ev.get("type") == "factbook_raw":
                        raw = ev["raw"]
                await db.commit()
        except Exception as e:
            print(f"  ❌ 采集失败: {e!r}")
            all_issues.append({"stock": f"{name}({code})", "field": "collect", "value": str(e),
                               "problem": f"采集整体失败: {e!r}", "severity": "high"})
            continue

        if raw is None:
            print("  ❌ 无数据返回")
            all_issues.append({"stock": f"{name}({code})", "field": "collect", "value": None,
                               "problem": "无 factbook_raw 事件", "severity": "high"})
            continue

        # 代码级检查（raw）
        issues = code_level_check(raw, code, name)
        if issues:
            print(f"  代码级检查发现 {len(issues)} 个问题")
            for iss in issues:
                print(f"    [{iss['severity']}] {iss['field']}: {iss['problem']}")
        else:
            print("  代码级检查通过 ✓")

        # 复刻事实 agent：用 orchestrator 的 _stream_fact_agent 产出 digest
        # （投资 agent 实际看到的是 digest，不是 raw——要验证 digest 质量）
        digest = ""
        if llm_ready:
            print("  事实 agent 消化中（产出 digest）...")
            try:
                from app.services.llm.manager import llm_manager
                orch = DebateOrchestrator(llm_manager.get(), db=None)
                target = {"name": name, "code": code, "type": "stock", "data": {}}
                async for ev in orch._stream_fact_agent(raw, target):
                    if ev.get("type") in ("factbook_done", "factbook"):
                        digest = ev.get("content", "")
                if digest:
                    print(f"  digest 产出完成（{len(digest)} 字）")
                else:
                    print("  ⚠️ digest 为空（fact-agent 可能失败）")
                    issues.append({"stock": f"{name}({code})", "field": "fact_agent_digest",
                                   "value": None, "problem": "事实 agent 产出 digest 为空",
                                   "severity": "high"})
            except Exception as e:
                print(f"  ⚠️ 事实 agent 失败: {e!r}")
                issues.append({"stock": f"{name}({code})", "field": "fact_agent",
                               "value": str(e), "problem": f"事实 agent 调用失败: {e!r}",
                               "severity": "high"})

        # LLM 审计（raw + digest，enable_thinking=True）
        if use_llm and llm_ready:
            print("  LLM 审计中（CPA 视角，enable_thinking）...")
            llm_result = await llm_validate(raw, digest, code, name, issues)
            if llm_result:
                trust = llm_result.get("trust", "unknown")
                llm_issues = llm_result.get("issues", [])
                print(f"  LLM 可信度: {trust}, 发现 {len(llm_issues)} 个问题")
                for li in llm_issues:
                    li["stock"] = f"{name}({code})"
                    li["source"] = "llm"
                    all_issues.append(li)
            else:
                print("  LLM 未配置或失败，跳过")

        all_issues.extend(issues)

    return all_issues


def write_report(issues: list[dict], round_num: int):
    """追加写入报告。"""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    high = [i for i in issues if i.get("severity") == "high"]
    medium = [i for i in issues if i.get("severity") == "medium"]
    low = [i for i in issues if i.get("severity") == "low"]

    with open(REPORT_FILE, "a", encoding="utf-8") as f:
        f.write(f"\n## Round {round_num} — {now}\n\n")
        f.write(f"总 issues: {len(issues)} (high={len(high)}, medium={len(medium)}, low={len(low)})\n\n")
        if high:
            f.write("### High severity\n\n")
            for iss in high:
                f.write(f"- **{iss['stock']}** `{iss.get('field','')}`: {iss.get('problem','')}"
                        f" (value={iss.get('value','')})"
                        + (f" → **fix: {iss['fix']}**" if iss.get("fix") else "") + "\n")
        if medium:
            f.write("\n### Medium severity\n\n")
            for iss in medium:
                f.write(f"- **{iss['stock']}** `{iss.get('field','')}`: {iss.get('problem','')}\n")
        if low:
            f.write("\n### Low severity\n\n")
            for iss in low:
                f.write(f"- **{iss['stock']}** `{iss.get('field','')}`: {iss.get('problem','')}\n")
        f.write("\n---\n")


async def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--n", type=int, default=5, help="每轮随机股票数")
    parser.add_argument("--no-llm", action="store_true", help="跳过 LLM 核验")
    parser.add_argument("--rounds", type=int, default=1, help="连续跑几轮")
    args = parser.parse_args()

    print(f"数据质量自迭代：{args.n} 只/轮 × {args.rounds} 轮，LLM={'off' if args.no_llm else 'on'}")
    total_issues = 0
    for r in range(1, args.rounds + 1):
        print(f"\n{'#'*60}\n# Round {r}\n{'#'*60}")
        issues = await run_one_round(n=args.n, use_llm=not args.no_llm)
        write_report(issues, r)
        total_issues += len(issues)
        print(f"\nRound {r} 汇总: {len(issues)} issues (报告追加到 {REPORT_FILE})")

    print(f"\n{'='*60}\n总计 {total_issues} issues，报告: {REPORT_FILE}")
    if total_issues == 0:
        print("🎉 无问题——数据质量通过！")
    else:
        print(f"⚠️ {total_issues} 个问题待修复——修后重跑验证。")


if __name__ == "__main__":
    asyncio.run(main())

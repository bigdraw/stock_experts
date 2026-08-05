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

async def llm_validate(raw: dict, stock_code: str, stock_name: str, code_issues: list) -> dict | None:
    """LLM 独立核验数据质量。返回 {issues, trust} 或 None（LLM 未配置）。"""
    try:
        from app.services.llm.manager import llm_manager
        from app.services.llm.provider import LLMMessage
        llm = llm_manager.get()
    except Exception:
        return None

    prompt = (
        "你是数据质量检验 agent。以下是一只 A 股股票的采集数据（JSON）+ 代码级检查结果。\n"
        "请独立核验：\n"
        "1. 数值合理性（PE/PB/ROE/股息率/CAGR 范围）\n"
        "2. 逻辑一致性（ROE vs ROIC、PE vs 增长率、分红率 vs 净利润）\n"
        "3. 明显错误（复数、None 应有值、季报值当年化用）\n"
        "4. 数据缺失项\n"
        "输出 JSON: {\"issues\": [{\"field\":\"\",\"problem\":\"\",\"severity\":\"high/medium/low\"}], \"trust\":\"high/medium/low\"}"
    )
    user = (f"标的：{stock_name}({stock_code})\n\n"
            f"代码级检查结果：{json.dumps(code_issues, ensure_ascii=False, default=str)}\n\n"
            f"原始数据（JSON）：\n{json.dumps(raw, ensure_ascii=False, default=str)[:8000]}")

    try:
        resp = await llm.chat([
            LLMMessage(role="system", content=prompt),
            LLMMessage(role="user", content=user),
        ], max_tokens=2000)
        # 尝试提取 JSON
        text = resp.content
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            return json.loads(text[start:end + 1])
    except Exception as e:
        logger.warning(f"LLM validate failed for {stock_code}: {e}")
    return None


# ─────────────────── 主循环 ───────────────────

async def run_one_round(n: int = 5, use_llm: bool = True) -> list[dict]:
    """一轮：随机抓取 → 代码级检查 → LLM 核验 → 返回所有 issues。"""
    await init_db()
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

        # 代码级检查
        issues = code_level_check(raw, code, name)
        if issues:
            print(f"  代码级检查发现 {len(issues)} 个问题")
            for iss in issues:
                print(f"    [{iss['severity']}] {iss['field']}: {iss['problem']}")
        else:
            print("  代码级检查通过 ✓")

        # LLM 核验
        if use_llm and issues:
            print("  LLM 核验中...")
            llm_result = await llm_validate(raw, code, name, issues)
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

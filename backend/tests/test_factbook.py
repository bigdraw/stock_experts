"""FactBook 测试：验证结构 + 校验 + 格式化（纯单元，不打外部数据源）。

测试范围只覆盖本次新增的 factbook 模块（不测未改动的 orchestrator 数据采集）。
采集器的网络/DB 部分用桩替换；重点验证 _validate 与 format 的逻辑。
"""

from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

# 确保能 import app.*
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.debate.factbook import FactBook


def _make_factbook_full() -> dict:
    """构造一份"数据完整且新鲜"的 FactBook。"""
    return {
        "stock_code": "600519",
        "stock_name": "贵州茅台",
        "collected_at": "2026-08-04T12:00:00",
        "value_analysis": {
            "latest": {
                "report_date": (date.today() - timedelta(days=30)).isoformat(),
                "roe": 30.0,
                "eps": 50.0,
                "roic": 18.0,
                "earnings_quality": 1.1,
            },
            "valuation": {"pe": 25.0, "pb": 8.0},
            "growth": {"revenue": {"cagr_5y": 0.15}},
            "trend": [{"report_date": "2026-03-31", "roe": 30.0}],
            "dividends": [{"dividend_per_share": 25.0}],
        },
        "kline": {
            "daily": {
                "summary": {
                    "last_close": 1700.0,
                    "change_1y": 5.0,
                    "change_5y": 80.0,
                    "annualized_5y": 12.5,
                    "max_drawdown_5y_pct": -25.0,
                    "near_5y_high": True,
                    "near_5y_low": False,
                    "volume_ratio_20d_vs_5y": 1.1,
                },
                "missing_days_30d": 0,
            },
            "weekly": {"summary": {"近52周": 15.0}},
            "monthly": {"summary": {"近60月(5年)": 80.0}},
        },
        "industry": "白酒行业增速放缓，茅台为龙头，定价权强。",
        "macro": "央行维持稳健货币政策，CPI 温和。",
        "market_regime": {"regime": "bull", "confidence": 0.62, "volatility_proxy": 18.0},
        "validation": {"status": "ok", "warnings": [], "errors": []},
    }


def test_validate_ok():
    """完整新鲜数据 → status=ok，无 warning/error。"""
    fb = _make_factbook_full()
    # 重算 validation（覆盖最新数据，不依赖手工填的 validation）
    fb["validation"] = FactBook()._validate(fb)
    assert fb["validation"]["status"] == "ok", fb["validation"]
    assert not fb["validation"]["warnings"]
    assert not fb["validation"]["errors"]
    print("✓ test_validate_ok passed")


def test_validate_stale_report():
    """财报距今 >120 天 → 警告过期。"""
    fb = _make_factbook_full()
    stale = (date.today() - timedelta(days=200)).isoformat()
    fb["value_analysis"]["latest"]["report_date"] = stale
    fb["validation"] = FactBook()._validate(fb)
    assert fb["validation"]["status"] == "warn"
    assert any("过期" in w for w in fb["validation"]["warnings"])


def test_validate_leverage_redflag():
    """ROE>0 但 ROIC<0 → 杠杆虚假回报警告。"""
    fb = _make_factbook_full()
    fb["value_analysis"]["latest"]["roic"] = -2.0
    fb["validation"] = FactBook()._validate(fb)
    assert any("杠杆" in w for w in fb["validation"]["warnings"])


def test_validate_value_analysis_error():
    """value_analysis 采集失败 → error（status=error）。"""
    fb = _make_factbook_full()
    fb["value_analysis"] = {"_error": "network timeout"}
    fb["validation"] = FactBook()._validate(fb)
    assert fb["validation"]["status"] == "error"
    assert any("价值分析失败" in e for e in fb["validation"]["errors"])


def test_format_contains_all_sections():
    """format 输出含所有 FactBook 维度节。"""
    fb = _make_factbook_full()
    out = FactBook().format(fb)
    for tag in [
        "<data_warnings>",
        "<target>",
        "<value_analysis>",
        "<kline_summary>",
        "<industry>",
        "<macro>",
        "<market_regime>",
    ]:
        assert tag in out, f"missing {tag} in format output"
    # trend 序列应被注入（不再丢掉）
    assert "trend" in out
    # 贵州茅台名应出现
    assert "贵州茅台" in out
    print("✓ test_format_contains_all_sections passed")


def test_format_truncation_removed():
    """format 不再截断到 1200 字符——完整 latest + trend 应都在。"""
    fb = _make_factbook_full()
    # 给 trend 多塞几期
    fb["value_analysis"]["trend"] = [
        {"report_date": f"2024-Q{i}", "roe": 30.0 + i, "revenue": 10000 * (i + 1)} for i in range(20)
    ]
    out = FactBook().format(fb)
    # 最末一期也应出现（若截断到 1200 字符会被砍掉）
    assert "2024-Q19" in out
    print("✓ test_format_truncation_removed passed")


def _run_all():
    test_validate_ok()
    test_validate_stale_report()
    test_validate_leverage_redflag()
    test_validate_value_analysis_error()
    test_format_contains_all_sections()
    test_format_truncation_removed()
    print("\n全部 FactBook 测试通过 ✓")


if __name__ == "__main__":
    _run_all()

"""Seed 默认投资 agent（idea8/10）。

每位 agent 的理念存独立文件 scripts/masters/*.md（frontmatter: name/description/config
+ body: 理念文本）。本脚本只放公共内容（工具调用 footer），读取各文件 + 追加 footer
后 idempotent 入库。type='master'。

用法：cd backend && PYTHONPATH=. uv run python scripts/seed_master_agents.py
启动时 main.py lifespan 自动调 seed_master_agents()。
"""

import asyncio
import json
import logging
import re
from pathlib import Path

from sqlalchemy import select

from app.database import async_session_factory
from app.models.agent import Agent

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

_MASTERS_DIR = Path(__file__).resolve().parent / "masters"

# 公共内容：工具调用描述（所有 agent 共用，不重复写进每个理念文件）
TOOL_FOOTER = """

## 可用工具（增强分析，基于数据自行判断，工具不替你下结论）

你是平台投资 agent，可调用以下工具获取数据支撑决策：

1. **stock-analysis 平台数据**：后端 http://127.0.0.1:8000 已实现一套股票/组合数据获取能力。
   先调 `GET /agent/tools`（需 Bearer token）查看完整清单。可取：
   - 个股价值分析：`GET /api/v1/stocks/{code}/value-analysis`（估值/盈利能力/财务安全/现金流/成长性/分红）
   - 行情/K线/财报：`GET /api/v1/stocks/{code}/quotes|financials|indicators`（K线支持日/周/月/季/年）
   - 回测/风险/信号/选股/市场状态：`/api/v1/quant/*`
2. **tavily 联网搜索**：搜索公司新闻、行业动态、宏观、财报披露等实时信息，补充定量数据之外的定性判断。

基于本理念 + 上述工具数据，给出你的分析判断。
"""


def _parse_md(path: Path) -> dict | None:
    """解析 masters/*.md：YAML frontmatter + body。"""
    text = path.read_text(encoding="utf-8")
    m = re.match(r"^---\n(.*?)\n---\n(.*)$", text, re.DOTALL)
    if not m:
        return None
    fm_raw, body = m.group(1), m.group(2).strip()
    fm = {}
    for line in fm_raw.splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            fm[k.strip()] = v.strip()
    config = {}
    if "config" in fm:
        try:
            config = json.loads(fm["config"])
        except json.JSONDecodeError:
            pass
    return {
        "name": fm.get("name", path.stem),
        "description": fm.get("description", ""),
        "config": config,
        "philosophy": body,
    }


def _load_masters() -> list[dict]:
    """读取 masters/ 下所有 .md 文件。"""
    masters = []
    if not _MASTERS_DIR.exists():
        return masters
    for path in sorted(_MASTERS_DIR.glob("*.md")):
        parsed = _parse_md(path)
        if parsed:
            masters.append(parsed)
            log.info(f"  loaded {path.name}: {parsed['name']}")
    return masters


async def seed_master_agents():
    """Idempotent: insert default master agents from masters/*.md if absent."""
    masters = _load_masters()
    if not masters:
        log.warning("No master .md files found; skipping seed.")
        return
    created = 0
    skipped = 0
    async with async_session_factory() as db:
        for spec in masters:
            existing = await db.execute(
                select(Agent).where(Agent.name == spec["name"], Agent.type == "master")
            )
            if existing.scalar_one_or_none() is not None:
                skipped += 1
                continue
            agent = Agent(
                name=spec["name"],
                type="master",
                description=spec["description"],
                system_prompt=spec["philosophy"] + TOOL_FOOTER,
                config=json.dumps(spec["config"], ensure_ascii=False),
            )
            db.add(agent)
            created += 1
            log.info(f"  created master agent: {spec['name']}")
        await db.commit()
    log.info(f"Master agents seed: {created} created, {skipped} skipped (already exist).")


if __name__ == "__main__":
    asyncio.run(seed_master_agents())

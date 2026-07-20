"""股票公司信息爬虫（idea19）——精简版：只提取公司简介/行业/板块。

同花顺（basic.10jqka.com.cn）为主源，新浪 F10 为备选。不用 LLM 生成。
"""

import logging
import re
from typing import Any

import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)
_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}


async def fetch_company_info(code: str) -> dict[str, Any]:
    """提取公司简介/行业/板块（同花顺主源，新浪备选）。"""
    info = await _fetch_10jqka(code)
    if not info.get("brief"):
        info2 = await _fetch_sina(code)
        for k, v in info2.items():
            if v and not info.get(k):
                info[k] = v
    return info


async def _fetch_10jqka(code: str) -> dict[str, Any]:
    info: dict[str, Any] = {}
    try:
        async with httpx.AsyncClient(timeout=10, headers=_HEADERS) as client:
            r = await client.get(f"http://basic.10jqka.com.cn/{code}/")
            if r.status_code != 200:
                return info
            r.encoding = "gbk"
            soup = BeautifulSoup(r.text, "html.parser")
            text = soup.get_text(separator="\n", strip=True)

            # 行业（申万行业）
            m = re.search(r"所属申万行业[：:]\s*([^\n]+)", text)
            if m:
                val = m.group(1).strip()
                if "所属" not in val and len(val) < 50:
                    info["industry"] = val

            # 主营业务（作为板块描述）
            m = re.search(r"主营业务[：:]\s*([^\n]+)", text)
            if m:
                val = m.group(1).strip()
                if len(val) < 200 and "所属" not in val:
                    info["sector"] = val

            # 公司简介
            idx = text.find("公司简介")
            if idx >= 0:
                snippet = text[idx + 4:idx + 500].strip()
                snippet = re.sub(r"了解更多.*", "", snippet, flags=re.DOTALL).strip()
                snippet = re.sub(r"\s+", " ", snippet)
                if len(snippet) > 10:
                    info["brief"] = snippet[:300]
    except Exception as e:
        logger.warning(f"10jqka failed for {code}: {e}")
    return info


async def _fetch_sina(code: str) -> dict[str, Any]:
    info: dict[str, Any] = {}
    try:
        async with httpx.AsyncClient(timeout=10, headers=_HEADERS) as client:
            r = await client.get(
                f"http://vip.stock.finance.sina.com.cn/corp/go.php/vCI_CorpBriefInfo/stockid/{code}.phtml"
            )
            if r.status_code != 200:
                return info
            r.encoding = "gbk"
            soup = BeautifulSoup(r.text, "html.parser")
            key_map = {"公司简介": "brief", "所属行业": "industry", "主营业务": "sector"}
            for td in soup.find_all("td"):
                t = td.get_text(strip=True)
                if t in key_map:
                    sib = td.find_next_sibling("td")
                    if sib:
                        val = sib.get_text(strip=True)[:300]
                        if val and val != "了解更多>>":
                            info[key_map[t]] = val
    except Exception as e:
        logger.warning(f"sina failed for {code}: {e}")
    return info

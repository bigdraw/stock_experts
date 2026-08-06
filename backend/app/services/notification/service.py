"""Notification and alert service."""

import logging
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.notification import Alert, Notification
from app.models.stock import FinancialReport, Stock
from app.services.filter.sandbox import FilterSandbox
from app.services.llm.provider import LLMMessage, LLMProvider

logger = logging.getLogger(__name__)


class AlertEngine:
    """Alert engine: create and evaluate user-defined alerts."""

    def __init__(self, db: AsyncSession, llm: LLMProvider):
        self.db = db
        self.llm = llm
        self.sandbox = FilterSandbox()

    async def create_alert(
        self,
        user_id: int,
        name: str,
        nl_condition: str,
        target_type: str | None = None,
        target_id: str | None = None,
    ) -> Alert:
        """Create alert from natural language condition."""
        code = await self._generate_condition_code(nl_condition)
        alert = Alert(
            user_id=user_id,
            name=name,
            nl_condition=nl_condition,
            condition_code=code,
            target_type=target_type,
            target_id=target_id,
        )
        self.db.add(alert)
        await self.db.flush()
        await self.db.refresh(alert)
        return alert

    async def check_alerts(self):
        """Check all active alerts (called by scheduler).

        Assembles the target's latest data per alert so the generated
        ``check(data)`` can read ``data['close']`` / ``data['pe_ratio']`` etc.
        (ISSUE-025: previously passed ``data={}`` → KeyError swallowed by the
        broad except → alerts never fired even when the scheduler ran).
        """
        result = await self.db.execute(select(Alert).where(Alert.is_active))
        alerts = result.scalars().all()

        for alert in alerts:
            try:
                data = await self._assemble_alert_data(alert)
                triggered = self._evaluate(alert.condition_code, data)
                if triggered:
                    await self._send_notification(
                        alert.user_id,
                        "alert",
                        f"告警触发：{alert.name}",
                        f"条件：{alert.nl_condition}\n时间：{datetime.now()}",
                    )
                    alert.last_triggered_at = datetime.now()
            except Exception as e:
                logger.warning(f"Alert {alert.id} evaluation failed: {e}")

        await self.db.flush()

    async def _assemble_alert_data(self, alert: Alert) -> dict:
        """Build the data dict the alert's ``check(data)`` expects (ISSUE-025).

        For a stock target, pull the latest 'Latest' financial snapshot and map
        the fields the generator prompt advertises (close/pe_ratio/pb_ratio/
        market_cap/...). Non-stock targets get an empty dict (condition may not
        fire, which is acceptable until portfolio/market data wiring is added).
        """
        data: dict = {}
        if alert.target_type == "stock" and alert.target_id:
            code = alert.target_id
            fr = (
                await self.db.execute(
                    select(FinancialReport)
                    .where(
                        FinancialReport.stock_code == code,
                        FinancialReport.report_type == "Latest",
                    )
                    .order_by(FinancialReport.report_date.desc())
                    .limit(1)
                )
            ).scalar_one_or_none()
            stock = await self.db.get(Stock, code)
            name = stock.name if stock else code
            if fr:
                data.update({
                    "code": code,
                    "name": name,
                    "close": fr.price,
                    "price": fr.price,
                    "open": fr.open,
                    "high": fr.high,
                    "low": fr.low,
                    "volume": fr.volume,
                    "amount": fr.amount,
                    "pe_ratio": fr.pe_ratio,
                    "pb_ratio": fr.pb_ratio,
                    "market_cap": fr.market_cap,
                    "turnoverratio": fr.turnoverratio,
                    "changepercent": fr.changepercent,
                })
            else:
                data.update({"code": code, "name": name})
        return data

    async def _generate_condition_code(self, nl_condition: str) -> str:
        response = await self.llm.chat(
            [
                LLMMessage(
                    role="system",
                    content="""生成告警检测 Python 函数。
函数签名：def check(data: dict) -> bool
data 包含股票最新数据（code, name, close, pe_ratio, pb_ratio, roe, market_cap 等）
返回 True 表示条件满足。只输出代码。""",
                ),
                LLMMessage(role="user", content=nl_condition),
            ]
        )
        import re

        code = re.search(r"```(?:python)?\s*\n(.*?)```", response.content, re.DOTALL)
        return code.group(1).strip() if code else response.content.strip()

    def _evaluate(self, code: str, data: dict) -> bool:
        """Evaluate an alert's LLM-generated ``check(data)`` in the sandbox.

        Routed through FilterSandbox.run_function (ISSUE-018): the previous
        bare ``exec`` with a hand-rolled ``__builtins__`` had no dunder guards,
        so a prompt-injected ``check`` could escape via
        ``().__class__.__subclasses__()`` and RCE. Now dunder access is blocked
        by RestrictedPython and pandas/numpy IO is AST-blocked.
        """
        try:
            return bool(self.sandbox.run_function(code, "check", (data,)))
        except Exception as e:
            logger.warning(f"Alert condition eval failed: {e}")
            return False

    async def _send_notification(self, user_id: int, type: str, title: str, content: str):
        self.db.add(Notification(user_id=user_id, type=type, title=title, content=content))
        await self.db.flush()


class SystemNotifier:
    """System notifications."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def notify(self, user_id: int, type: str, title: str, content: str):
        self.db.add(Notification(user_id=user_id, type=type, title=title, content=content))
        await self.db.flush()

    async def backup_reminder(self):
        from app.models.user import User

        result = await self.db.execute(select(User))
        for user in result.scalars():
            await self.notify(
                user.id, "system", "数据库备份提醒", "本周数据库备份时间已到，请确认备份状态。"
            )

    async def data_acquisition_alert(self, status: str, details: str):
        from app.models.user import User

        result = await self.db.execute(select(User).where(User.role == "admin"))
        for admin in result.scalars():
            await self.notify(admin.id, "system", f"数据采集异常：{status}", details)

"""Notification and alert service."""

import json
import logging
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.notification import Alert, Notification
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
        self, user_id: int, name: str, nl_condition: str,
        target_type: str | None = None, target_id: str | None = None,
    ) -> Alert:
        """Create alert from natural language condition."""
        code = await self._generate_condition_code(nl_condition)
        alert = Alert(
            user_id=user_id, name=name, nl_condition=nl_condition,
            condition_code=code, target_type=target_type, target_id=target_id,
        )
        self.db.add(alert)
        await self.db.flush()
        await self.db.refresh(alert)
        return alert

    async def check_alerts(self):
        """Check all active alerts (called by scheduler)."""
        result = await self.db.execute(select(Alert).where(Alert.is_active == True))
        alerts = result.scalars().all()

        for alert in alerts:
            try:
                triggered = self._evaluate(alert.condition_code, {})
                if triggered:
                    await self._send_notification(
                        alert.user_id, "alert",
                        f"告警触发：{alert.name}",
                        f"条件：{alert.nl_condition}\n时间：{datetime.now()}",
                    )
                    alert.last_triggered_at = datetime.now()
            except Exception as e:
                logger.warning(f"Alert {alert.id} evaluation failed: {e}")

        await self.db.flush()

    async def _generate_condition_code(self, nl_condition: str) -> str:
        response = await self.llm.chat([
            LLMMessage(role="system", content="""生成告警检测 Python 函数。
函数签名：def check(data: dict) -> bool
data 包含股票最新数据（code, name, close, pe_ratio, pb_ratio, roe, market_cap 等）
返回 True 表示条件满足。只输出代码。"""),
            LLMMessage(role="user", content=nl_condition),
        ])
        import re
        code = re.search(r"```(?:python)?\s*\n(.*?)```", response.content, re.DOTALL)
        return code.group(1).strip() if code else response.content.strip()

    def _evaluate(self, code: str, data: dict) -> bool:
        safe_globals = {"__builtins__": {"len": len, "float": float, "int": int, "str": str, "bool": bool, "True": True, "False": False, "None": None}}
        exec(code, safe_globals)
        check_fn = safe_globals.get("check")
        return bool(check_fn(data)) if check_fn else False

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
            await self.notify(user.id, "system", "数据库备份提醒", "本周数据库备份时间已到，请确认备份状态。")

    async def data_acquisition_alert(self, status: str, details: str):
        from app.models.user import User
        result = await self.db.execute(select(User).where(User.role == "admin"))
        for admin in result.scalars():
            await self.notify(admin.id, "system", f"数据采集异常：{status}", details)

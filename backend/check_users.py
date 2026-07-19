import asyncio
from app.database import get_db
from app.models.user import User
from sqlalchemy import select

async def check_users():
    async for db in get_db():
        result = await db.execute(select(User))
        users = result.scalars().all()
        print(f'Total users: {len(users)}')
        for u in users:
            print(f'  - {u.username} (role: {u.role}, active: {u.is_active})')

if __name__ == "__main__":
    asyncio.run(check_users())

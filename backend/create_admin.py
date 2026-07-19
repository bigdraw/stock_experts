import asyncio
from app.database import get_db
from app.models.user import User
from app.utils.security import hash_password
from sqlalchemy import select

async def create_admin():
    async for db in get_db():
        # Check if admin already exists
        result = await db.execute(select(User).where(User.username == "admin"))
        admin = result.scalar_one_or_none()
        
        if admin:
            print(f"Admin already exists: {admin.username}")
            # Reset password to ***REMOVED***
            admin.password_hash = hash_password("***REMOVED***")
            admin.role = "admin"
            admin.is_active = True
            await db.commit()
            print(f"Admin password reset to '***REMOVED***'")
        else:
            # Create new admin
            admin = User(
                username="admin",
                password_hash=hash_password("***REMOVED***"),
                role="admin",
                is_active=True
            )
            db.add(admin)
            await db.commit()
            print(f"Admin created: admin / ***REMOVED***")

if __name__ == "__main__":
    asyncio.run(create_admin())

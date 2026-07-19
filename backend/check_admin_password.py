import asyncio
from app.database import get_db
from app.models.user import User
from app.utils.security import verify_password
from sqlalchemy import select

async def check_admin_password():
    async for db in get_db():
        result = await db.execute(select(User).where(User.username == "admin"))
        admin = result.scalar_one_or_none()
        
        if admin:
            print(f"Admin user found: {admin.username}")
            print(f"Password hash: {admin.password_hash[:20]}...")
            
            # Test common passwords
            test_passwords = ["admin", "admin123", "123456", "password"]
            for pwd in test_passwords:
                if verify_password(pwd, admin.password_hash):
                    print(f"[PASS] Password '{pwd}' is correct!")
                    return
            print("[FAIL] None of the common passwords match")
        else:
            print("[FAIL] Admin user not found")

if __name__ == "__main__":
    asyncio.run(check_admin_password())

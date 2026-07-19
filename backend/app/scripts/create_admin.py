"""Script to create the first admin user."""

import asyncio
import sys

from sqlalchemy import select

from app.database import async_session_factory
from app.models.user import User
from app.utils.security import hash_password


async def create_admin(username: str, password: str):
    """Create an admin user."""
    async with async_session_factory() as db:
        # Check if user already exists
        result = await db.execute(select(User).where(User.username == username))
        existing = result.scalar_one_or_none()
        
        if existing:
            # Update existing user to admin
            existing.role = "admin"
            existing.is_active = True
            await db.commit()
            print(f"✓ User '{username}' updated to admin role")
        else:
            # Create new admin user
            admin = User(
                username=username,
                password_hash=hash_password(password),
                role="admin",
                is_active=True
            )
            db.add(admin)
            await db.commit()
            print(f"✓ Admin user '{username}' created successfully")


if __name__ == "__main__":
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    
    if len(sys.argv) < 3:
        print("Usage: python -m app.scripts.create_admin <username> <password>")
        print("Example: python -m app.scripts.create_admin admin admin123")
        sys.exit(1)
    
    username = sys.argv[1]
    password = sys.argv[2]
    
    if len(password) < 6:
        print("Error: Password must be at least 6 characters")
        sys.exit(1)
    
    asyncio.run(create_admin(username, password))

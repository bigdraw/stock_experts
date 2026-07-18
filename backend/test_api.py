"""
Comprehensive API test script for Stock Analysis Platform
Tests all major features: auth, stocks, portfolios, filters, backtest, debate, notifications
"""

import asyncio
import httpx
import json
import sys
from typing import Optional

BASE_URL = "http://127.0.0.1:8000/api/v1"
TIMEOUT = 30.0

class TestResult:
    def __init__(self, name: str, passed: bool, error: Optional[str] = None, details: Optional[str] = None):
        self.name = name
        self.passed = passed
        self.error = error
        self.details = details

results = []

def log_result(result: TestResult):
    results.append(result)
    status = "[PASS]" if result.passed else "[FAIL]"
    print(f"{status}: {result.name}")
    if result.error:
        print(f"  Error: {result.error}")
    if result.details:
        print(f"  Details: {result.details}")

async def test_health():
    """Test backend health endpoint"""
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            resp = await client.get("http://127.0.0.1:8000/health")
            if resp.status_code == 200 and resp.json().get("status") == "ok":
                log_result(TestResult("Health Check", True))
                return True
            else:
                log_result(TestResult("Health Check", False, f"Status: {resp.status_code}"))
                return False
    except Exception as e:
        log_result(TestResult("Health Check", False, str(e)))
        return False

async def test_register():
    """Test user registration"""
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            resp = await client.post(
                f"{BASE_URL}/auth/register",
                json={"username": "testuser", "password": "testpass123"}
            )
            if resp.status_code == 200:
                data = resp.json()
                log_result(TestResult("Register", True, details=f"User ID: {data.get('id')}"))
                return data
            elif resp.status_code == 400 and "already exists" in resp.text:
                log_result(TestResult("Register", True, details="User already exists (OK)"))
                return {"id": None, "username": "testuser"}
            else:
                log_result(TestResult("Register", False, f"Status: {resp.status_code}", resp.text))
                return None
    except Exception as e:
        log_result(TestResult("Register", False, str(e)))
        return None

async def test_login():
    """Test user login"""
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            resp = await client.post(
                f"{BASE_URL}/auth/login",
                json={"username": "testuser", "password": "testpass123"}
            )
            if resp.status_code == 200:
                data = resp.json()
                token = data.get("access_token")
                log_result(TestResult("Login", True, details=f"Token: {token[:20]}..."))
                return token
            else:
                log_result(TestResult("Login", False, f"Status: {resp.status_code}", resp.text))
                return None
    except Exception as e:
        log_result(TestResult("Login", False, str(e)))
        return None

async def test_get_me(token: str):
    """Test get current user"""
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            resp = await client.get(
                f"{BASE_URL}/auth/me",
                headers={"Authorization": f"Bearer {token}"}
            )
            if resp.status_code == 200:
                data = resp.json()
                log_result(TestResult("Get Me", True, details=f"Username: {data.get('username')}"))
                return True
            else:
                log_result(TestResult("Get Me", False, f"Status: {resp.status_code}", resp.text))
                return False
    except Exception as e:
        log_result(TestResult("Get Me", False, str(e)))
        return False

async def test_list_stocks(token: str):
    """Test list stocks"""
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            resp = await client.get(
                f"{BASE_URL}/stocks",
                headers={"Authorization": f"Bearer {token}"},
                params={"limit": 10}
            )
            if resp.status_code == 200:
                data = resp.json()
                log_result(TestResult("List Stocks", True, details=f"Count: {len(data)}"))
                return True
            else:
                log_result(TestResult("List Stocks", False, f"Status: {resp.status_code}", resp.text))
                return False
    except Exception as e:
        log_result(TestResult("List Stocks", False, str(e)))
        return False

async def test_create_portfolio(token: str):
    """Test create portfolio"""
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            resp = await client.post(
                f"{BASE_URL}/portfolios",
                headers={"Authorization": f"Bearer {token}"},
                json={"name": "Test Portfolio", "description": "Test description"}
            )
            if resp.status_code == 200:
                data = resp.json()
                portfolio_id = data.get("id")
                log_result(TestResult("Create Portfolio", True, details=f"ID: {portfolio_id}"))
                return portfolio_id
            else:
                log_result(TestResult("Create Portfolio", False, f"Status: {resp.status_code}", resp.text))
                return None
    except Exception as e:
        log_result(TestResult("Create Portfolio", False, str(e)))
        return None

async def test_list_portfolios(token: str):
    """Test list portfolios"""
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            resp = await client.get(
                f"{BASE_URL}/portfolios",
                headers={"Authorization": f"Bearer {token}"}
            )
            if resp.status_code == 200:
                data = resp.json()
                log_result(TestResult("List Portfolios", True, details=f"Count: {len(data)}"))
                return True
            else:
                log_result(TestResult("List Portfolios", False, f"Status: {resp.status_code}", resp.text))
                return False
    except Exception as e:
        log_result(TestResult("List Portfolios", False, str(e)))
        return False

async def test_list_filters(token: str):
    """Test list filters"""
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            resp = await client.get(
                f"{BASE_URL}/filters",
                headers={"Authorization": f"Bearer {token}"}
            )
            if resp.status_code == 200:
                data = resp.json()
                log_result(TestResult("List Filters", True, details=f"Count: {len(data)}"))
                return True
            else:
                log_result(TestResult("List Filters", False, f"Status: {resp.status_code}", resp.text))
                return False
    except Exception as e:
        log_result(TestResult("List Filters", False, str(e)))
        return False

async def test_list_agents(token: str):
    """Test list agents"""
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            resp = await client.get(
                f"{BASE_URL}/agents",
                headers={"Authorization": f"Bearer {token}"}
            )
            if resp.status_code == 200:
                data = resp.json()
                log_result(TestResult("List Agents", True, details=f"Count: {len(data)}"))
                return True
            else:
                log_result(TestResult("List Agents", False, f"Status: {resp.status_code}", resp.text))
                return False
    except Exception as e:
        log_result(TestResult("List Agents", False, str(e)))
        return False

async def test_list_strategies(token: str):
    """Test list backtest strategies"""
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            resp = await client.get(
                f"{BASE_URL}/backtest/strategies",
                headers={"Authorization": f"Bearer {token}"}
            )
            if resp.status_code == 200:
                data = resp.json()
                log_result(TestResult("List Strategies", True, details=f"Count: {len(data)}"))
                return True
            else:
                log_result(TestResult("List Strategies", False, f"Status: {resp.status_code}", resp.text))
                return False
    except Exception as e:
        log_result(TestResult("List Strategies", False, str(e)))
        return False

async def test_list_notifications(token: str):
    """Test list notifications"""
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            resp = await client.get(
                f"{BASE_URL}/notifications",
                headers={"Authorization": f"Bearer {token}"}
            )
            if resp.status_code == 200:
                data = resp.json()
                log_result(TestResult("List Notifications", True, details=f"Count: {len(data)}"))
                return True
            else:
                log_result(TestResult("List Notifications", False, f"Status: {resp.status_code}", resp.text))
                return False
    except Exception as e:
        log_result(TestResult("List Notifications", False, str(e)))
        return False

async def test_unread_count(token: str):
    """Test unread notification count"""
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            resp = await client.get(
                f"{BASE_URL}/notifications/unread-count",
                headers={"Authorization": f"Bearer {token}"}
            )
            if resp.status_code == 200:
                data = resp.json()
                log_result(TestResult("Unread Count", True, details=f"Count: {data.get('count')}"))
                return True
            else:
                log_result(TestResult("Unread Count", False, f"Status: {resp.status_code}", resp.text))
                return False
    except Exception as e:
        log_result(TestResult("Unread Count", False, str(e)))
        return False

async def main():
    print("=" * 60)
    print("Stock Analysis Platform - API Test Suite")
    print("=" * 60)
    print()
    
    # Test health
    print("1. Testing backend health...")
    if not await test_health():
        print("\nBackend is not running or not accessible!")
        sys.exit(1)
    
    print("\n2. Testing authentication...")
    # Try to register (may fail if user exists)
    user = await test_register()
    
    # Login
    token = await test_login()
    if not token:
        print("\nCannot proceed without valid token!")
        sys.exit(1)
    
    # Get current user
    await test_get_me(token)
    
    print("\n3. Testing stock APIs...")
    await test_list_stocks(token)
    
    print("\n4. Testing portfolio APIs...")
    portfolio_id = await test_create_portfolio(token)
    await test_list_portfolios(token)
    
    print("\n5. Testing filter APIs...")
    await test_list_filters(token)
    
    print("\n6. Testing agent APIs...")
    await test_list_agents(token)
    
    print("\n7. Testing backtest APIs...")
    await test_list_strategies(token)
    
    print("\n8. Testing notification APIs...")
    await test_list_notifications(token)
    await test_unread_count(token)
    
    # Summary
    print("\n" + "=" * 60)
    print("Test Summary")
    print("=" * 60)
    passed = sum(1 for r in results if r.passed)
    failed = sum(1 for r in results if not r.passed)
    print(f"Total: {len(results)}")
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")
    
    if failed > 0:
        print("\nFailed tests:")
        for r in results:
            if not r.passed:
                print(f"  - {r.name}: {r.error}")
        sys.exit(1)
    else:
        print("\n[OK] All tests passed!")
        sys.exit(0)

if __name__ == "__main__":
    asyncio.run(main())

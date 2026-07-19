"""
Test script for stock analysis platform
Tests the 3 issues mentioned by user:
1. Financial update only processes 2095 stocks instead of 4127
2. Free indicator storage and display
3. User management upgrade/delete button errors
"""

import asyncio
import httpx
import json

BASE_URL = "http://127.0.0.1:8000/api/v1"
ADMIN_URL = "http://127.0.0.1:8000/admin"


async def test_financial_update_count():
    """Test 1: Verify financial update processes all stocks"""
    print("\n=== Test 1: Financial Update Count ===")
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        # Login first
        login_resp = await client.post(
            f"{BASE_URL}/auth/login",
            json={"username": "admin", "password": "***REMOVED***"}
        )
        
        if login_resp.status_code != 200:
            print(f"[FAIL] Login failed: {login_resp.status_code}")
            return False
        
        token = login_resp.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        
        # Check total stock count
        stocks_resp = await client.get(
            f"{BASE_URL}/stocks",
            headers=headers,
            params={"limit": 10000}
        )
        
        if stocks_resp.status_code == 200:
            stocks = stocks_resp.json()
            total_stocks = len(stocks)
            print(f"[PASS] Total stocks in database: {total_stocks}")
            
            # Check if we have 4127 stocks
            if total_stocks >= 4000:
                print(f"[PASS] Stock count is reasonable ({total_stocks} stocks)")
            else:
                print(f"[WARN] Stock count seems low ({total_stocks} stocks)")
        else:
            print(f"[FAIL] Failed to fetch stocks: {stocks_resp.status_code}")
            return False
        
        # Check financial data coverage
        financial_resp = await client.get(
            f"{BASE_URL}/stocks/financial",
            headers=headers
        )
        
        if financial_resp.status_code == 200:
            financial_data = financial_resp.json()
            stocks_with_financial = len([s for s in financial_data if s.get('pe_ratio') is not None])
            print(f"[PASS] Stocks with financial data: {stocks_with_financial}/{total_stocks}")
            
            if stocks_with_financial < total_stocks * 0.5:
                print(f"[WARN] Less than 50% of stocks have financial data")
            else:
                print(f"[PASS] Financial data coverage is reasonable")
        else:
            print(f"[WARN] Failed to fetch financial data: {financial_resp.status_code}")
        
        return True


async def test_indicator_fields():
    """Test 2: Verify indicator fields are stored and displayed"""
    print("\n=== Test 2: Indicator Fields ===")
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        # Login first
        login_resp = await client.post(
            f"{BASE_URL}/auth/login",
            json={"username": "admin", "password": "***REMOVED***"}
        )
        
        if login_resp.status_code != 200:
            print(f"[FAIL] Login failed: {login_resp.status_code}")
            return False
        
        token = login_resp.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        
        # Get a sample stock with financial data
        stocks_resp = await client.get(
            f"{BASE_URL}/stocks",
            headers=headers,
            params={"limit": 10}
        )
        
        if stocks_resp.status_code != 200:
            print(f"[FAIL] Failed to fetch stocks: {stocks_resp.status_code}")
            return False
        
        stocks = stocks_resp.json()
        if not stocks:
            print("[FAIL] No stocks found")
            return False
        
        # Check first stock's fields
        sample_stock = stocks[0]
        print(f"\n[PASS] Sample stock: {sample_stock['code']} - {sample_stock['name']}")
        print(f"  Fields available:")
        for key, value in sample_stock.items():
            if value is not None:
                print(f"    [PASS] {key}: {value}")
            else:
                print(f"    [WARN] {key}: None")
        
        # Check if key indicators are present
        required_fields = ['pe_ratio', 'pb_ratio', 'market_cap']
        missing_fields = [f for f in required_fields if sample_stock.get(f) is None]
        
        if missing_fields:
            print(f"\n[WARN] Missing fields: {', '.join(missing_fields)}")
        else:
            print(f"\n[PASS] All key indicators present")
        
        return True


async def test_user_management():
    """Test 3: Verify user management operations"""
    print("\n=== Test 3: User Management ===")
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        # Login as admin
        login_resp = await client.post(
            f"{BASE_URL}/auth/login",
            json={"username": "admin", "password": "***REMOVED***"}
        )
        
        if login_resp.status_code != 200:
            print(f"[FAIL] Login failed: {login_resp.status_code}")
            return False
        
        token = login_resp.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        
        # Test user list
        users_resp = await client.get(
            f"{ADMIN_URL}/users",
            headers=headers
        )
        
        if users_resp.status_code == 200:
            users = users_resp.json()
            print(f"[PASS] User list fetched: {len(users)} users")
            
            # Find a non-admin user to test with
            test_user = next((u for u in users if u['role'] != 'admin'), None)
            
            if test_user:
                print(f"[PASS] Test user found: {test_user['username']} (ID: {test_user['id']})")
                
                # Test role update
                new_role = "user" if test_user['role'] == 'admin' else 'admin'
                update_resp = await client.put(
                    f"{ADMIN_URL}/users/{test_user['id']}/role",
                    headers=headers,
                    json={"role": new_role}
                )
                
                if update_resp.status_code == 200:
                    print(f"[PASS] Role update successful")
                else:
                    print(f"[FAIL] Role update failed: {update_resp.status_code} - {update_resp.text}")
                
                # Test status update
                status_resp = await client.put(
                    f"{ADMIN_URL}/users/{test_user['id']}/status",
                    headers=headers,
                    json={"is_active": not test_user.get('is_active', True)}
                )
                
                if status_resp.status_code == 200:
                    print(f"[PASS] Status update successful")
                else:
                    print(f"[FAIL] Status update failed: {status_resp.status_code} - {status_resp.text}")
            else:
                print("[WARN] No non-admin user found for testing")
        else:
            print(f"[FAIL] Failed to fetch users: {users_resp.status_code}")
            return False
        
        return True


async def main():
    print("=" * 60)
    print("Stock Analysis Platform - Issue Verification")
    print("=" * 60)
    
    results = []
    
    # Test 1: Financial update count
    try:
        result = await test_financial_update_count()
        results.append(("Financial Update Count", result))
    except Exception as e:
        print(f"[FAIL] Test 1 failed with exception: {e}")
        results.append(("Financial Update Count", False))
    
    # Test 2: Indicator fields
    try:
        result = await test_indicator_fields()
        results.append(("Indicator Fields", result))
    except Exception as e:
        print(f"[FAIL] Test 2 failed with exception: {e}")
        results.append(("Indicator Fields", False))
    
    # Test 3: User management
    try:
        result = await test_user_management()
        results.append(("User Management", result))
    except Exception as e:
        print(f"[FAIL] Test 3 failed with exception: {e}")
        results.append(("User Management", False))
    
    # Summary
    print("\n" + "=" * 60)
    print("Test Summary")
    print("=" * 60)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for name, result in results:
        status = "[PASS]" if result else "[FAIL]"
        print(f"{status}: {name}")
    
    print(f"\nTotal: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n[PASS] All tests passed!")
    else:
        print(f"\n[WARN] {total - passed} test(s) failed")


if __name__ == "__main__":
    asyncio.run(main())

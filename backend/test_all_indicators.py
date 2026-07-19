"""Test script to verify all indicator fields are returned."""

import asyncio
import httpx

BASE_URL = "http://127.0.0.1:8000"


async def test_all_indicators():
    """Test that all indicator fields are returned."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        # Login first
        login_resp = await client.post(
            f"{BASE_URL}/api/v1/auth/login",
            json={"username": "admin", "password": "***REMOVED***"}
        )
        
        if login_resp.status_code != 200:
            print(f"[FAIL] Login failed: {login_resp.status_code}")
            return False
        
        token = login_resp.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        
        # Test the endpoint
        print("\n=== Testing /stocks/with-indicators endpoint ===")
        resp = await client.get(
            f"{BASE_URL}/api/v1/stocks/with-indicators",
            headers=headers,
            params={"limit": 5}
        )
        
        if resp.status_code != 200:
            print(f"[FAIL] Request failed: {resp.status_code}")
            print(f"Response: {resp.text}")
            return False
        
        stocks = resp.json()
        print(f"[PASS] Fetched {len(stocks)} stocks")
        
        if stocks:
            sample = stocks[0]
            print(f"\nSample stock: {sample['code']} - {sample['name']}")
            print(f"\nAll fields:")
            
            # Group fields by category
            basic_fields = ['code', 'name', 'market', 'industry', 'sector', 'is_active']
            price_fields = ['price', 'open', 'high', 'low', 'settlement', 'change', 'change_pct']
            volume_fields = ['volume', 'amount', 'turnover_ratio']
            valuation_fields = ['pe_ratio', 'pb_ratio']
            market_cap_fields = ['market_cap', 'circulating_market_cap']
            derived_fields = ['is_profitable']
            
            print("\n  基本信息:")
            for field in basic_fields:
                value = sample.get(field)
                print(f"    {field}: {value}")
            
            print("\n  行情指标:")
            for field in price_fields:
                value = sample.get(field)
                print(f"    {field}: {value}")
            
            print("\n  成交指标:")
            for field in volume_fields:
                value = sample.get(field)
                if field == 'amount' and value:
                    print(f"    {field}: {value:,.0f} 元 ({value/100000000:.2f} 亿元)")
                elif field == 'volume' and value:
                    print(f"    {field}: {value:,.0f} 股")
                else:
                    print(f"    {field}: {value}")
            
            print("\n  估值指标:")
            for field in valuation_fields:
                value = sample.get(field)
                print(f"    {field}: {value}")
            
            print("\n  市值指标:")
            for field in market_cap_fields:
                value = sample.get(field)
                if value:
                    print(f"    {field}: {value:,.2f} 万元 ({value/10000:.2f} 亿元)")
                else:
                    print(f"    {field}: {value}")
            
            print("\n  衍生指标:")
            for field in derived_fields:
                value = sample.get(field)
                print(f"    {field}: {value}")
            
            # Check which fields have data
            all_fields = basic_fields + price_fields + volume_fields + valuation_fields + market_cap_fields + derived_fields
            fields_with_data = sum(1 for f in all_fields if sample.get(f) is not None)
            
            print(f"\n[INFO] Fields with data: {fields_with_data}/{len(all_fields)}")
            
            return True
        else:
            print("[WARN] No stocks returned")
            return False


if __name__ == "__main__":
    result = asyncio.run(test_all_indicators())
    if result:
        print("\n[PASS] Test passed!")
    else:
        print("\n[FAIL] Test failed!")

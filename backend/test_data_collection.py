"""Test script to trigger a small data collection and verify all fields."""

import asyncio
import httpx

BASE_URL = "http://127.0.0.1:8000"


async def test_data_collection():
    """Test triggering a data collection and verify all fields are populated."""
    async with httpx.AsyncClient(timeout=60.0) as client:
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
        
        # Trigger a full basic collection
        print("\n=== Triggering data collection ===")
        collect_resp = await client.post(
            f"{BASE_URL}/api/v1/data/collect/full",
            headers=headers
        )
        
        if collect_resp.status_code != 200:
            print(f"[FAIL] Collection trigger failed: {collect_resp.status_code}")
            print(f"Response: {collect_resp.text}")
            return False
        
        task_id = collect_resp.json().get("task_id")
        print(f"[PASS] Collection started with task_id: {task_id}")
        
        # Wait for collection to complete
        print("\nWaiting for collection to complete...")
        for i in range(30):  # Wait up to 30 seconds
            await asyncio.sleep(2)
            
            # Check task status
            status_resp = await client.get(
                f"{BASE_URL}/api/v1/tasks/{task_id}",
                headers=headers
            )
            
            if status_resp.status_code == 200:
                task = status_resp.json()
                status = task.get("status")
                print(f"  Status: {status}, Progress: {task.get('current', 0)}/{task.get('total', 0)}")
                
                if status in ["completed", "failed"]:
                    break
            else:
                print(f"  Failed to get status: {status_resp.status_code}")
        
        # Now check if the data was populated
        print("\n=== Checking collected data ===")
        stocks_resp = await client.get(
            f"{BASE_URL}/api/v1/stocks/with-indicators",
            headers=headers,
            params={"limit": 5, "search": "000"}
        )
        
        if stocks_resp.status_code != 200:
            print(f"[FAIL] Failed to fetch stocks: {stocks_resp.status_code}")
            return False
        
        stocks = stocks_resp.json()
        print(f"[PASS] Fetched {len(stocks)} stocks")
        
        if stocks:
            sample = stocks[0]
            print(f"\nSample stock: {sample['code']} - {sample['name']}")
            
            # Check which fields have data
            price_fields = ['price', 'open', 'high', 'low', 'settlement', 'change', 'change_pct']
            volume_fields = ['volume', 'amount', 'turnover_ratio']
            valuation_fields = ['pe_ratio', 'pb_ratio']
            market_cap_fields = ['market_cap', 'circulating_market_cap']
            
            print("\n  行情指标:")
            for field in price_fields:
                value = sample.get(field)
                status = "[OK]" if value is not None else "[--]"
                print(f"    {status} {field}: {value}")
            
            print("\n  成交指标:")
            for field in volume_fields:
                value = sample.get(field)
                status = "[OK]" if value is not None else "[--]"
                if field == 'amount' and value:
                    print(f"    {status} {field}: {value:,.0f} yuan ({value/100000000:.2f} yi)")
                elif field == 'volume' and value:
                    print(f"    {status} {field}: {value:,.0f} shares")
                else:
                    print(f"    {status} {field}: {value}")
            
            print("\n  估值指标:")
            for field in valuation_fields:
                value = sample.get(field)
                status = "[OK]" if value is not None else "[--]"
                print(f"    {status} {field}: {value}")
            
            print("\n  市值指标:")
            for field in market_cap_fields:
                value = sample.get(field)
                status = "[OK]" if value is not None else "[--]"
                if value:
                    print(f"    {status} {field}: {value:,.2f} wan-yuan ({value/10000:.2f} yi)")
                else:
                    print(f"    {status} {field}: {value}")
            
            # Count fields with data
            all_indicator_fields = price_fields + volume_fields + valuation_fields + market_cap_fields
            fields_with_data = sum(1 for f in all_indicator_fields if sample.get(f) is not None)
            
            print(f"\n[INFO] Indicator fields with data: {fields_with_data}/{len(all_indicator_fields)}")
            
            if fields_with_data >= 10:  # At least 10 out of 13 fields should have data
                print("[PASS] Most fields populated")
                return True
            else:
                print("[WARN] Many fields still empty")
                return False
        else:
            print("[WARN] No stocks returned")
            return False


if __name__ == "__main__":
    result = asyncio.run(test_data_collection())
    if result:
        print("\n[PASS] Test passed!")
    else:
        print("\n[FAIL] Test failed!")

import httpx
import asyncio

async def test_admin_api():
    async with httpx.AsyncClient() as client:
        # First login
        login_resp = await client.post(
            'http://127.0.0.1:8000/api/v1/auth/login',
            json={'username': 'admin', 'password': '***REMOVED***'}
        )
        
        if login_resp.status_code != 200:
            print(f'Login failed: {login_resp.status_code}')
            return
        
        token = login_resp.json()['access_token']
        headers = {'Authorization': f'Bearer {token}'}
        
        # Test admin API
        r = await client.get('http://127.0.0.1:8000/admin/users', headers=headers)
        print(f'Admin API Status: {r.status_code}')
        print(f'Response: {r.text[:500]}')

asyncio.run(test_admin_api())

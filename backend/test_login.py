import httpx
import asyncio

async def test_login():
    async with httpx.AsyncClient() as client:
        r = await client.post('http://127.0.0.1:8000/api/v1/auth/login', 
                            json={'username': 'admin', 'password': '***REMOVED***'})
        print(f'Status: {r.status_code}')
        print(f'Response: {r.text}')

asyncio.run(test_login())

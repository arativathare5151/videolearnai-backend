import httpx
from config import settings

SUPABASE_URL = settings.SUPABASE_URL
SUPABASE_KEY = settings.SUPABASE_SERVICE_ROLE_KEY

# New Supabase API key format requires these specific headers
HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=representation",
    "X-Client-Info": "supabase-py/2.0",
}

async def db_insert(table: str, data: dict) -> dict:
    async with httpx.AsyncClient() as client:
        res = await client.post(
            f"{SUPABASE_URL}/rest/v1/{table}",
            headers=HEADERS,
            json=data,
        )
        res.raise_for_status()
        result = res.json()
        return result[0] if isinstance(result, list) else result

async def db_update(table: str, data: dict, match: dict) -> dict:
    params = {k: f"eq.{v}" for k, v in match.items()}
    async with httpx.AsyncClient() as client:
        res = await client.patch(
            f"{SUPABASE_URL}/rest/v1/{table}",
            headers=HEADERS,
            params=params,
            json=data,
        )
        res.raise_for_status()
        return res.json()

async def db_select(table: str, match: dict = None, select: str = "*") -> list:
    params = {"select": select}
    if match:
        for k, v in match.items():
            params[k] = f"eq.{v}"
    async with httpx.AsyncClient() as client:
        res = await client.get(
            f"{SUPABASE_URL}/rest/v1/{table}",
            headers=HEADERS,
            params=params,
        )
        res.raise_for_status()
        return res.json()

async def db_select_single(table: str, match: dict, select: str = "*") -> dict:
    rows = await db_select(table, match, select)
    return rows[0] if rows else None
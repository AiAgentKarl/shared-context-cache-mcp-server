"""HTTP-Client fuer den Shared Context Cache (agent-apis.vercel.app/api/cache)."""

import httpx

CACHE_BASE_URL = "https://agent-apis.vercel.app/api/cache"

# Standard-Timeout in Sekunden
TIMEOUT = 15


async def get_cache_entry(key: str) -> dict:
    """Ruft einen Cache-Eintrag per Key ab."""
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        resp = await client.get(CACHE_BASE_URL, params={"action": "get", "key": key})
        resp.raise_for_status()
        return resp.json()


async def search_cache(query: str, limit: int = 10) -> dict:
    """Sucht im Cache nach passenden Eintraegen (Stichwortsuche)."""
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        resp = await client.get(
            CACHE_BASE_URL,
            params={"action": "search", "query": query, "limit": limit},
        )
        resp.raise_for_status()
        return resp.json()


async def store_cache_entry(
    key: str,
    value: dict | str | list,
    ttl: int = 86400,
    tags: list[str] | None = None,
    agent_id: str = "mcp-agent",
) -> dict:
    """Speichert einen neuen Eintrag im Cache."""
    payload: dict = {
        "action": "store",
        "key": key,
        "value": value,
        "ttl": ttl,
        "agent_id": agent_id,
    }
    if tags:
        payload["tags"] = tags
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        resp = await client.post(CACHE_BASE_URL, json=payload)
        resp.raise_for_status()
        return resp.json()


async def get_cache_stats() -> dict:
    """Gibt Statistiken ueber den Cache zurueck (Hits, Misses, Top-Queries)."""
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        resp = await client.get(CACHE_BASE_URL, params={"action": "stats"})
        resp.raise_for_status()
        return resp.json()


async def list_cache_entries(limit: int = 20, tags: list[str] | None = None) -> dict:
    """Listet alle Cache-Eintraege auf, optional gefiltert nach Tags."""
    params: dict = {"action": "list", "limit": limit}
    if tags:
        params["tags"] = ",".join(tags)
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        resp = await client.get(CACHE_BASE_URL, params=params)
        resp.raise_for_status()
        return resp.json()

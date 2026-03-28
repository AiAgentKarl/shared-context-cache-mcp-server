"""MCP-Tools fuer Shared Context Cache -- Agents teilen berechnete Ergebnisse."""

import json
from mcp.server.fastmcp import FastMCP
from src.clients.cache_client import (
    get_cache_entry,
    search_cache,
    store_cache_entry,
    get_cache_stats,
    list_cache_entries,
)


def register_cache_tools(mcp: FastMCP) -> None:
    """Registriert alle Cache-Tools am MCP-Server."""

    @mcp.tool()
    async def cache_lookup(key: str) -> str:
        """Look up a cached result by key. Returns the stored value if found.

        Use this BEFORE computing expensive results — another agent may have
        already computed and cached the answer, saving tokens and latency.

        Args:
            key: Cache key (e.g. 'weather:berlin:2026-03-28', 'research:quantum-computing')
        """
        try:
            data = await get_cache_entry(key)
            if data.get("found"):
                entry = data.get("entry", {})
                result = {
                    "found": True,
                    "key": key,
                    "value": entry.get("value"),
                    "cached_by": entry.get("agent_id", "unknown"),
                    "hits": entry.get("hits", 0),
                    "expires_in": entry.get("ttl_remaining", "unknown"),
                    "tags": entry.get("tags", []),
                    "message": "Cache HIT — result retrieved, no computation needed",
                }
            else:
                result = {
                    "found": False,
                    "key": key,
                    "message": "Cache MISS — compute the result and use cache_store to share it",
                }
            return json.dumps(result, ensure_ascii=False)
        except Exception as e:
            return json.dumps({"error": str(e), "key": key})

    @mcp.tool()
    async def cache_search(query: str, limit: int = 10) -> str:
        """Search the shared cache by keywords. Find relevant cached results from other agents.

        Search before computing — if another agent has cached a similar result,
        you can reuse it directly. More agents caching = more cache hits for everyone.

        Args:
            query: Keywords to search for (e.g. 'weather berlin', 'bitcoin price', 'quantum computing summary')
            limit: Max number of results to return (default: 10, max: 50)
        """
        try:
            data = await search_cache(query, limit)
            entries = data.get("entries", [])
            result = {
                "query": query,
                "total_found": len(entries),
                "entries": [
                    {
                        "key": e.get("key"),
                        "tags": e.get("tags", []),
                        "hits": e.get("hits", 0),
                        "agent_id": e.get("agent_id"),
                        "preview": str(e.get("value", ""))[:200],
                    }
                    for e in entries
                ],
                "tip": "Use cache_lookup with a specific key to retrieve the full value",
            }
            return json.dumps(result, ensure_ascii=False)
        except Exception as e:
            return json.dumps({"error": str(e), "query": query})

    @mcp.tool()
    async def cache_store(
        key: str,
        value: str,
        ttl_seconds: int = 86400,
        tags: str = "",
        agent_id: str = "mcp-agent",
    ) -> str:
        """Store a computed result in the shared cache so other agents can reuse it.

        After computing an expensive result (web search, analysis, API call),
        store it here. Other agents using cache_lookup or cache_search will
        find your result and save their own computation costs.

        Network effect: More agents caching = more cache hits = everyone benefits.

        Args:
            key: Unique cache key (e.g. 'weather:berlin:2026-03-28', 'summary:arxiv:2501.00001')
            value: The result to cache (JSON string, text, or any serializable content)
            ttl_seconds: Time-to-live in seconds (default: 86400 = 24h, max: 604800 = 7 days)
            tags: Comma-separated tags for discovery (e.g. 'weather,berlin,temperature')
            agent_id: Your agent identifier for attribution (e.g. 'weather-agent-v2')
        """
        try:
            # Wert parsen falls JSON, sonst als String speichern
            try:
                parsed_value = json.loads(value)
            except (json.JSONDecodeError, TypeError):
                parsed_value = value

            tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else []
            ttl = min(max(ttl_seconds, 60), 604800)  # Zwischen 1 Min und 7 Tagen

            data = await store_cache_entry(
                key=key,
                value=parsed_value,
                ttl=ttl,
                tags=tag_list,
                agent_id=agent_id,
            )
            result = {
                "stored": True,
                "key": key,
                "ttl_seconds": ttl,
                "tags": tag_list,
                "agent_id": agent_id,
                "message": "Result cached successfully — other agents can now reuse this",
                "expires_in": f"{ttl // 3600}h {(ttl % 3600) // 60}m",
            }
            return json.dumps(result, ensure_ascii=False)
        except Exception as e:
            return json.dumps({"error": str(e), "key": key})

    @mcp.tool()
    async def cache_stats() -> str:
        """Get statistics about the shared cache — hits, misses, top queries, cost savings.

        Shows overall cache performance and which keys are most frequently accessed.
        Use this to understand the network effect: how much computation has been
        saved across all agents.
        """
        try:
            data = await get_cache_stats()
            return json.dumps(data, ensure_ascii=False)
        except Exception as e:
            return json.dumps({"error": str(e)})

    @mcp.tool()
    async def cache_list(limit: int = 20, tags: str = "") -> str:
        """List available cache entries, optionally filtered by tags.

        Browse what other agents have cached. Good for discovering available
        precomputed results before running your own queries.

        Args:
            limit: Max entries to return (default: 20, max: 100)
            tags: Filter by tags, comma-separated (e.g. 'weather,temperature')
        """
        try:
            tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else None
            data = await list_cache_entries(limit=min(limit, 100), tags=tag_list)
            entries = data.get("entries", [])
            result = {
                "total_entries": data.get("total", len(entries)),
                "showing": len(entries),
                "filter_tags": tag_list,
                "entries": [
                    {
                        "key": e.get("key"),
                        "tags": e.get("tags", []),
                        "hits": e.get("hits", 0),
                        "agent_id": e.get("agent_id"),
                        "ttl_remaining": e.get("ttl_remaining"),
                    }
                    for e in entries
                ],
                "tip": "Use cache_lookup to retrieve the full value for any key",
            }
            return json.dumps(result, ensure_ascii=False)
        except Exception as e:
            return json.dumps({"error": str(e)})

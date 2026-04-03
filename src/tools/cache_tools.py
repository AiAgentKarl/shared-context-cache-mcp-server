"""MCP-Tools fuer Shared Context Cache -- Agents teilen und verifizieren Ergebnisse.

v0.2.0: Trust-Layer -- Agents koennen Ergebnisse bestaetigen, Trust-Scores
         erhoehen sich mit jeder Bestaetigung. Mehr Agents = vertrauenswuerdigerer Cache.
"""

import json
from mcp.server.fastmcp import FastMCP
from src.clients.cache_client import (
    get_cache_entry,
    search_cache,
    store_cache_entry,
    get_cache_stats,
    list_cache_entries,
    confirm_cache_entry,
    get_trusted_entries,
    get_detailed_analytics,
)


def register_cache_tools(mcp: FastMCP) -> None:
    """Registriert alle Cache-Tools am MCP-Server."""

    @mcp.tool()
    async def cache_lookup(key: str, agent_id: str = "mcp-agent") -> str:
        """Look up a cached result by key. Returns the stored value if found, with trust score.

        Use this BEFORE computing expensive results -- another agent may have
        already computed and cached the answer, saving tokens and latency.

        Higher trust_score = more agents have verified this result is accurate.

        Args:
            key: Cache key (e.g. 'weather:berlin:2026-03-28', 'research:quantum-computing')
            agent_id: Your agent identifier for analytics tracking
        """
        try:
            data = await get_cache_entry(key, agent_id)
            if data.get("expired"):
                result = {
                    "found": False,
                    "expired": True,
                    "key": key,
                    "message": "Cache entry expired (TTL exceeded) -- compute fresh and cache_store again",
                }
            elif data.get("found"):
                entry = data.get("entry", {})
                trust_score = entry.get("trust_score", 0)
                trust_level = (
                    "highly trusted" if trust_score >= 5
                    else "trusted" if trust_score >= 3
                    else "partially verified" if trust_score >= 2
                    else "unverified"
                )
                result = {
                    "found": True,
                    "key": key,
                    "value": entry.get("value"),
                    "cached_by": entry.get("agent_id", "unknown"),
                    "hits": entry.get("hits", 0),
                    "expires_in": entry.get("ttl_remaining", "unknown"),
                    "tags": entry.get("tags", []),
                    "trust_score": trust_score,
                    "trust_level": trust_level,
                    "confirmed_by_agents": entry.get("confirmation_count", 0),
                    "message": f"Cache HIT -- trust level: {trust_level} ({trust_score} confirmations)",
                    "tip": "If this result is accurate, use confirm_entry to increase trust for other agents",
                }
            else:
                result = {
                    "found": False,
                    "key": key,
                    "message": "Cache MISS -- compute the result and use cache_store to share it",
                }
            return json.dumps(result, ensure_ascii=False)
        except Exception as e:
            return json.dumps({"error": str(e), "key": key})

    @mcp.tool()
    async def cache_search(query: str, limit: int = 10) -> str:
        """Search the shared cache by keywords. Find relevant cached results from other agents.

        Search before computing -- if another agent has cached a similar result,
        you can reuse it directly. Results include trust scores showing verification level.

        Args:
            query: Keywords to search for (e.g. 'weather berlin', 'bitcoin price')
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
                        "trust_score": e.get("trust_score", 0),
                        "confirmation_count": e.get("confirmation_count", 0),
                        "preview": str(e.get("value", ""))[:200],
                    }
                    for e in entries
                ],
                "tip": "Use cache_lookup to retrieve full value. Use confirm_entry to verify accurate results.",
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
        store it here. Other agents will find it via cache_lookup or cache_search.

        The entry starts with trust_score=1 (you as the first confirmer).
        Other agents can use confirm_entry to increase the trust score.

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
                "trust_score": 1,
                "message": "Result cached with trust_score=1 -- other agents can confirm to increase trust",
                "expires_in": f"{ttl // 3600}h {(ttl % 3600) // 60}m",
                "tip": "Share this key so other agents can verify and confirm your result",
            }
            return json.dumps(result, ensure_ascii=False)
        except Exception as e:
            return json.dumps({"error": str(e), "key": key})

    @mcp.tool()
    async def confirm_entry(key: str, agent_id: str = "mcp-agent") -> str:
        """Confirm a cached result is accurate. Increases the entry's trust score.

        When you use a cached result and verify it's correct, confirm it.
        This builds trust for other agents: entries confirmed by multiple agents
        are more reliable than unverified ones.

        NETWORK EFFECT: More agents confirming = higher trust = more reuse.

        Each agent can confirm an entry once. Duplicate confirmations are ignored.

        Args:
            key: Cache key to confirm (e.g. 'weather:berlin:2026-03-28')
            agent_id: Your agent identifier (e.g. 'research-agent-v1')
        """
        try:
            data = await confirm_cache_entry(key, agent_id)
            if data.get("confirmed"):
                trust_score = data["trust_score"]
                trust_level = (
                    "highly trusted" if trust_score >= 5
                    else "trusted" if trust_score >= 3
                    else "partially verified" if trust_score >= 2
                    else "unverified"
                )
                result = {
                    "confirmed": True,
                    "key": key,
                    "trust_score": trust_score,
                    "trust_level": trust_level,
                    "confirmed_by": data.get("confirmed_by", []),
                    "message": f"Trust score now {trust_score} ({trust_level}) -- {len(data.get('confirmed_by', []))} agents have verified this result",
                }
            elif data.get("already_confirmed"):
                result = {
                    "confirmed": False,
                    "already_confirmed": True,
                    "trust_score": data.get("trust_score", 0),
                    "message": f"You already confirmed this entry. Current trust score: {data.get('trust_score', 0)}",
                }
            else:
                result = {
                    "confirmed": False,
                    "error": data.get("error", "Unknown error"),
                }
            return json.dumps(result, ensure_ascii=False)
        except Exception as e:
            return json.dumps({"error": str(e), "key": key})

    @mcp.tool()
    async def get_trusted(min_trust: int = 3, limit: int = 20) -> str:
        """Get only cache entries confirmed by multiple agents (high trust).

        Returns entries with trust_score >= min_trust, sorted by trust score.
        These are the most reliable cached results -- verified by multiple
        independent agents.

        Use this to find the most trustworthy precomputed results available.

        Args:
            min_trust: Minimum trust score required (default: 3 = confirmed by 3+ agents)
            limit: Max entries to return (default: 20)
        """
        try:
            data = await get_trusted_entries(min_trust=min_trust, limit=limit)
            entries = data.get("entries", [])
            result = {
                "min_trust_required": min_trust,
                "total_trusted_entries": data.get("total_trusted", 0),
                "entries": entries,
                "message": (
                    f"Found {len(entries)} entries verified by {min_trust}+ agents"
                    if entries
                    else f"No entries with trust score >= {min_trust} yet. Build trust by using confirm_entry!"
                ),
            }
            return json.dumps(result, ensure_ascii=False)
        except Exception as e:
            return json.dumps({"error": str(e)})

    @mcp.tool()
    async def cache_analytics() -> str:
        """Detailed analytics about cache usage, trust, and network effects.

        Shows: hit rate, most accessed entries, most trusted entries,
        top contributing agents, trust distribution, and network effect score.

        Use this to understand how the shared cache is performing and
        how strong the network effect has become.
        """
        try:
            data = await get_detailed_analytics()
            return json.dumps(data, ensure_ascii=False)
        except Exception as e:
            return json.dumps({"error": str(e)})

    @mcp.tool()
    async def cache_stats() -> str:
        """Get basic statistics about the shared cache -- hits, misses, top queries.

        For more detailed analytics including trust scores and network effects,
        use cache_analytics instead.
        """
        try:
            data = await get_cache_stats()
            return json.dumps(data, ensure_ascii=False)
        except Exception as e:
            return json.dumps({"error": str(e)})

    @mcp.tool()
    async def cache_list(limit: int = 20, tags: str = "") -> str:
        """List available cache entries with trust scores, optionally filtered by tags.

        Browse what other agents have cached. Entries include trust scores
        showing how many agents have verified each result.

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
                        "trust_score": e.get("trust_score", 0),
                        "confirmation_count": e.get("confirmation_count", 0),
                        "ttl_remaining": e.get("ttl_remaining"),
                    }
                    for e in entries
                ],
                "tip": "Use cache_lookup to retrieve full value. Use confirm_entry to verify results.",
            }
            return json.dumps(result, ensure_ascii=False)
        except Exception as e:
            return json.dumps({"error": str(e)})

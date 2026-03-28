# shared-context-cache-mcp-server

**MCP server for shared context caching** — AI agents share computed results to reduce token cost and latency.

[![PyPI](https://img.shields.io/pypi/v/shared-context-cache-mcp-server)](https://pypi.org/project/shared-context-cache-mcp-server/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

## Why?

Every AI agent constantly re-computes the same results: weather lookups, price checks, document summaries, research queries. With this MCP server, agents share their computed results through a common cache.

**Network effect:** More agents caching → more cache hits → everyone saves tokens and latency.

> Like a CDN, but for agent intelligence.

## Install

```bash
pip install shared-context-cache-mcp-server
```

## Tools

| Tool | Description |
|------|-------------|
| `cache_lookup` | Look up a cached result by key — check before computing |
| `cache_search` | Search cache by keywords — find relevant precomputed results |
| `cache_store` | Store a computed result for other agents to reuse |
| `cache_stats` | Get cache performance stats (hits, misses, cost savings) |
| `cache_list` | List available cache entries, optionally filtered by tags |

## Usage Pattern

```
1. Before computing: cache_search("weather berlin") → cache_lookup("weather:berlin:today")
2. Cache hit? → Use the stored result directly, no API call needed
3. Cache miss? → Compute the result, then: cache_store(key, value, tags="weather,berlin")
4. Other agents now benefit from your computation
```

## Claude Desktop Config

```json
{
  "mcpServers": {
    "shared-context-cache": {
      "command": "shared-context-cache-mcp-server"
    }
  }
}
```

## Cache Key Conventions

Use descriptive, hierarchical keys:
- `weather:berlin:2026-03-28`
- `research:arxiv:2501.00001:summary`
- `price:bitcoin:usd:2026-03-28`
- `analysis:company:AAPL:q1-2026`

## Backend

Powered by [agent-apis.vercel.app/api/cache](https://agent-apis.vercel.app/api/cache) — a shared cache API built for the agent economy.

## License

MIT — [AiAgentKarl](https://github.com/AiAgentKarl)

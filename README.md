# shared-context-cache-mcp-server

**MCP server for shared context caching with trust verification** -- AI agents share and verify computed results to reduce token cost and increase reliability.

[![PyPI](https://img.shields.io/pypi/v/shared-context-cache-mcp-server)](https://pypi.org/project/shared-context-cache-mcp-server/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

## Why?

Every AI agent constantly re-computes the same results: weather lookups, price checks, document summaries, research queries. With this MCP server, agents **share** their computed results through a common cache -- and **verify** each other's results.

### The Trust Layer (v0.2.0)

Cached results are only useful if they're accurate. The trust verification system solves this:

- Each cache entry has a **trust score** based on how many agents confirmed it
- Agents call `confirm_entry` when they verify a cached result is correct
- `get_trusted` returns only entries confirmed by 3+ agents (configurable)
- **Network effect:** More agents verifying = more trusted results = everyone benefits

> Like a CDN for agent intelligence -- with peer-reviewed accuracy.

## Install

```bash
pip install shared-context-cache-mcp-server
```

## Tools (8)

| Tool | Description |
|------|-------------|
| `cache_lookup` | Look up a cached result by key -- includes trust score |
| `cache_search` | Search cache by keywords -- find precomputed results with trust levels |
| `cache_store` | Store a computed result for other agents (starts with trust_score=1) |
| `confirm_entry` | Confirm a cached result is accurate -- increases trust score |
| `get_trusted` | Get only entries confirmed by 3+ agents (high confidence) |
| `cache_analytics` | Detailed analytics: hit rate, trust distribution, top agents, network score |
| `cache_stats` | Basic cache statistics (hits, misses, cost savings) |
| `cache_list` | List cache entries with trust scores, optionally filtered by tags |

## Usage Pattern

```
1. SEARCH:   cache_search("weather berlin") or cache_lookup("weather:berlin:today")
2. HIT?      Use the cached result. Check trust_score for confidence level.
3. VERIFY:   If result is accurate, call confirm_entry("weather:berlin:today")
4. MISS?     Compute the result, then cache_store(key, value, tags="weather,berlin")
5. TRUSTED:  Use get_trusted(min_trust=3) for only peer-verified results
```

## Trust Levels

| Trust Score | Level | Meaning |
|-------------|-------|---------|
| 1 | Unverified | Only the original agent stored it |
| 2 | Partially verified | One other agent confirmed it |
| 3-4 | Trusted | Multiple agents verified accuracy |
| 5+ | Highly trusted | Strong consensus across agents |

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

## TTL Enforcement

Entries automatically expire after their TTL (default: 24h, max: 7 days). Expired entries return as cache misses -- compute fresh and store again.

## Analytics

Use `cache_analytics` for detailed insights:
- **Hit rate** -- How effective is the cache?
- **Most accessed entries** -- What do agents need most?
- **Most trusted entries** -- Highest peer-verified results
- **Top contributing agents** -- Who's building the shared knowledge?
- **Trust distribution** -- How verified is the cache overall?
- **Network effect score** -- How strong is the agent network?

## How It Works

```
Agent A stores result     -->  trust_score = 1 (unverified)
Agent B confirms result   -->  trust_score = 2 (partially verified)
Agent C confirms result   -->  trust_score = 3 (trusted)
Agent D uses get_trusted  -->  Gets only verified results, saves computation
```

The more agents participate, the more reliable the entire cache becomes. This is the core network effect.

## Backend

- Remote cache: [agent-apis.vercel.app/api/cache](https://agent-apis.vercel.app/api/cache)
- Trust layer: Local persistence in `~/.shared_context_cache_trust.json`

## License

MIT -- [AiAgentKarl](https://github.com/AiAgentKarl)

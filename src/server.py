"""Shared Context Cache MCP-Server -- Agents teilen und verifizieren Ergebnisse."""

from mcp.server.fastmcp import FastMCP
from src.tools.cache_tools import register_cache_tools

# FastMCP-Server initialisieren
mcp = FastMCP(
    "Shared Context Cache",
    instructions=(
        "Shared context cache with trust verification for AI agents. "
        "Before computing expensive results (web searches, analyses, API calls), "
        "use cache_search or cache_lookup to check if another agent has already "
        "computed the answer. After computing, use cache_store to share your result. "
        "TRUST LAYER: When you use a cached result and verify it's correct, "
        "call confirm_entry to increase its trust score. Entries confirmed by "
        "multiple agents are more reliable. Use get_trusted for high-confidence results. "
        "Network effect: more agents caching AND confirming = more trusted results = "
        "everyone saves tokens with confidence."
    ),
)

# Cache-Tools registrieren
register_cache_tools(mcp)


def main() -> None:
    """Einstiegspunkt fuer den MCP-Server (stdio-Transport)."""
    mcp.run()


if __name__ == "__main__":
    main()

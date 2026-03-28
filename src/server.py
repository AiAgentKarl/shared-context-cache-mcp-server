"""Shared Context Cache MCP-Server -- Agents teilen berechnete Ergebnisse."""

from mcp.server.fastmcp import FastMCP
from src.tools.cache_tools import register_cache_tools

# FastMCP-Server initialisieren
mcp = FastMCP(
    "Shared Context Cache",
    instructions=(
        "Shared context cache for AI agents. Before computing expensive results "
        "(web searches, analyses, API calls), use cache_search or cache_lookup to "
        "check if another agent has already computed the answer. After computing, "
        "use cache_store to share your result with other agents. "
        "Network effect: more agents caching = more cache hits = everyone saves tokens."
    ),
)

# Cache-Tools registrieren
register_cache_tools(mcp)


def main() -> None:
    """Einstiegspunkt fuer den MCP-Server (stdio-Transport)."""
    mcp.run()


if __name__ == "__main__":
    main()

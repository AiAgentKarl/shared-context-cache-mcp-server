"""HTTP-Client fuer den Shared Context Cache (agent-apis.vercel.app/api/cache).

Erweitert um lokales Trust-Layer: Trust-Scores, Confirmations und Analytics
werden lokal persistiert in ~/.shared_context_cache_trust.json
"""

import json
import time
from pathlib import Path

import httpx

CACHE_BASE_URL = "https://agent-apis.vercel.app/api/cache"

# Standard-Timeout in Sekunden
TIMEOUT = 15

# Lokaler Trust-Store (persistiert Trust-Scores und Analytics)
TRUST_STORE_PATH = Path.home() / ".shared_context_cache_trust.json"


def _load_trust_store() -> dict:
    """Laedt den lokalen Trust-Store von Disk."""
    if TRUST_STORE_PATH.exists():
        try:
            return json.loads(TRUST_STORE_PATH.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return _default_trust_store()
    return _default_trust_store()


def _default_trust_store() -> dict:
    """Erstellt einen leeren Trust-Store mit Standardstruktur."""
    return {
        "entries": {},  # key -> {trust_score, confirmations: [agent_ids], created_at, last_confirmed}
        "analytics": {
            "total_lookups": 0,
            "total_stores": 0,
            "total_confirmations": 0,
            "total_hits": 0,
            "total_misses": 0,
            "agent_contributions": {},  # agent_id -> {stores, confirmations, lookups}
            "access_log": [],  # [{key, action, agent_id, timestamp}] -- letzte 500
        },
    }


def _save_trust_store(store: dict) -> None:
    """Speichert den Trust-Store auf Disk."""
    try:
        TRUST_STORE_PATH.write_text(
            json.dumps(store, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except OSError:
        pass  # Schreibfehler ignorieren, nicht kritisch


def _track_access(store: dict, key: str, action: str, agent_id: str = "unknown") -> None:
    """Trackt einen Zugriff im Analytics-Log (max 500 Eintraege)."""
    log_entry = {
        "key": key,
        "action": action,
        "agent_id": agent_id,
        "timestamp": time.time(),
    }
    store["analytics"]["access_log"].append(log_entry)
    # Nur die letzten 500 Eintraege behalten
    if len(store["analytics"]["access_log"]) > 500:
        store["analytics"]["access_log"] = store["analytics"]["access_log"][-500:]

    # Agent-Contributions tracken
    if agent_id not in store["analytics"]["agent_contributions"]:
        store["analytics"]["agent_contributions"][agent_id] = {
            "stores": 0,
            "confirmations": 0,
            "lookups": 0,
        }
    contrib = store["analytics"]["agent_contributions"][agent_id]
    if action == "store":
        contrib["stores"] += 1
    elif action == "confirm":
        contrib["confirmations"] += 1
    elif action in ("lookup", "search"):
        contrib["lookups"] += 1


def _get_entry_trust(store: dict, key: str) -> dict:
    """Gibt Trust-Daten fuer einen Cache-Eintrag zurueck."""
    if key in store["entries"]:
        return store["entries"][key]
    return {"trust_score": 0, "confirmations": [], "created_at": None, "last_confirmed": None}


def _is_expired(entry_trust: dict, ttl_seconds: int | None = None) -> bool:
    """Prueft ob ein Eintrag abgelaufen ist basierend auf TTL."""
    if not entry_trust.get("stored_at"):
        return False  # Kein Zeitstempel, kein TTL-Check moeglich
    if ttl_seconds is None:
        ttl_seconds = entry_trust.get("ttl_seconds", 86400)
    elapsed = time.time() - entry_trust["stored_at"]
    return elapsed > ttl_seconds


async def get_cache_entry(key: str, agent_id: str = "unknown") -> dict:
    """Ruft einen Cache-Eintrag per Key ab. Prueft TTL-Ablauf lokal."""
    store = _load_trust_store()

    # Analytics tracken
    store["analytics"]["total_lookups"] += 1
    _track_access(store, key, "lookup", agent_id)

    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        resp = await client.get(CACHE_BASE_URL, params={"action": "get", "key": key})
        resp.raise_for_status()
        data = resp.json()

    if data.get("found"):
        # TTL-Enforcement: lokal pruefen ob abgelaufen
        entry_trust = _get_entry_trust(store, key)
        if _is_expired(entry_trust):
            store["analytics"]["total_misses"] += 1
            _save_trust_store(store)
            return {
                "found": False,
                "expired": True,
                "message": "Entry existed but TTL has expired",
            }

        store["analytics"]["total_hits"] += 1
        # Trust-Daten an Antwort anhaengen
        entry = data.get("entry", {})
        entry["trust_score"] = entry_trust.get("trust_score", 0)
        entry["confirmations"] = entry_trust.get("confirmations", [])
        entry["confirmation_count"] = len(entry_trust.get("confirmations", []))
        data["entry"] = entry
    else:
        store["analytics"]["total_misses"] += 1

    _save_trust_store(store)
    return data


async def search_cache(query: str, limit: int = 10) -> dict:
    """Sucht im Cache nach passenden Eintraegen (Stichwortsuche)."""
    store = _load_trust_store()
    _track_access(store, query, "search")

    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        resp = await client.get(
            CACHE_BASE_URL,
            params={"action": "search", "query": query, "limit": limit},
        )
        resp.raise_for_status()
        data = resp.json()

    # Trust-Scores an Suchergebnisse anhaengen
    entries = data.get("entries", [])
    for entry in entries:
        key = entry.get("key", "")
        entry_trust = _get_entry_trust(store, key)
        entry["trust_score"] = entry_trust.get("trust_score", 0)
        entry["confirmation_count"] = len(entry_trust.get("confirmations", []))
        # Abgelaufene Eintraege markieren
        if _is_expired(entry_trust):
            entry["expired"] = True

    # Abgelaufene rausfiltern
    data["entries"] = [e for e in entries if not e.get("expired")]
    _save_trust_store(store)
    return data


async def store_cache_entry(
    key: str,
    value: dict | str | list,
    ttl: int = 86400,
    tags: list[str] | None = None,
    agent_id: str = "mcp-agent",
) -> dict:
    """Speichert einen neuen Eintrag im Cache. Initialisiert Trust-Score."""
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
        data = resp.json()

    # Trust-Store aktualisieren
    store = _load_trust_store()
    store["analytics"]["total_stores"] += 1
    _track_access(store, key, "store", agent_id)

    # Neuen Eintrag im Trust-Store anlegen (oder aktualisieren)
    store["entries"][key] = {
        "trust_score": 1,  # Ersteller zaehlt als erste Confirmation
        "confirmations": [agent_id],
        "created_at": time.time(),
        "stored_at": time.time(),
        "ttl_seconds": ttl,
        "last_confirmed": time.time(),
        "stored_by": agent_id,
        "tags": tags or [],
    }

    _save_trust_store(store)
    return data


async def confirm_cache_entry(key: str, agent_id: str) -> dict:
    """Bestaetigt einen Cache-Eintrag als korrekt. Erhoeht Trust-Score.

    Jeder Agent kann einen Eintrag einmal bestaetigen.
    Mehrfach-Bestaetigungen vom gleichen Agent werden ignoriert.
    """
    store = _load_trust_store()

    # Pruefen ob Eintrag existiert
    if key not in store["entries"]:
        # Eintrag im Remote-Cache pruefen
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            resp = await client.get(CACHE_BASE_URL, params={"action": "get", "key": key})
            resp.raise_for_status()
            data = resp.json()

        if not data.get("found"):
            return {
                "confirmed": False,
                "error": f"Entry '{key}' not found in cache",
            }

        # Eintrag lokal anlegen falls nur remote vorhanden
        entry = data.get("entry", {})
        store["entries"][key] = {
            "trust_score": 0,
            "confirmations": [],
            "created_at": time.time(),
            "stored_at": time.time(),
            "ttl_seconds": entry.get("ttl", 86400),
            "last_confirmed": None,
            "stored_by": entry.get("agent_id", "unknown"),
            "tags": entry.get("tags", []),
        }

    entry_trust = store["entries"][key]

    # TTL-Check
    if _is_expired(entry_trust):
        return {
            "confirmed": False,
            "error": f"Entry '{key}' has expired (TTL exceeded)",
        }

    # Duplikat-Check: Jeder Agent kann nur einmal bestaetigen
    if agent_id in entry_trust["confirmations"]:
        return {
            "confirmed": False,
            "already_confirmed": True,
            "trust_score": entry_trust["trust_score"],
            "message": f"Agent '{agent_id}' has already confirmed this entry",
        }

    # Confirmation eintragen
    entry_trust["confirmations"].append(agent_id)
    entry_trust["trust_score"] = len(entry_trust["confirmations"])
    entry_trust["last_confirmed"] = time.time()

    # Analytics tracken
    store["analytics"]["total_confirmations"] += 1
    _track_access(store, key, "confirm", agent_id)

    _save_trust_store(store)

    return {
        "confirmed": True,
        "key": key,
        "trust_score": entry_trust["trust_score"],
        "confirmation_count": len(entry_trust["confirmations"]),
        "confirmed_by": entry_trust["confirmations"],
        "message": f"Trust score increased to {entry_trust['trust_score']}",
    }


async def get_trusted_entries(min_trust: int = 3, limit: int = 20) -> dict:
    """Gibt nur Eintraege zurueck, die von mindestens min_trust Agents bestaetigt wurden."""
    store = _load_trust_store()

    trusted = []
    for key, entry_trust in store["entries"].items():
        # Abgelaufene ueberspringen
        if _is_expired(entry_trust):
            continue
        if entry_trust["trust_score"] >= min_trust:
            trusted.append({
                "key": key,
                "trust_score": entry_trust["trust_score"],
                "confirmation_count": len(entry_trust["confirmations"]),
                "confirmed_by": entry_trust["confirmations"],
                "stored_by": entry_trust.get("stored_by", "unknown"),
                "tags": entry_trust.get("tags", []),
                "created_at": entry_trust.get("created_at"),
                "last_confirmed": entry_trust.get("last_confirmed"),
            })

    # Nach Trust-Score sortieren (hoechster zuerst)
    trusted.sort(key=lambda x: x["trust_score"], reverse=True)
    trusted = trusted[:limit]

    return {
        "min_trust": min_trust,
        "total_trusted": len(trusted),
        "entries": trusted,
    }


async def get_detailed_analytics() -> dict:
    """Gibt detaillierte Cache-Analytics zurueck."""
    store = _load_trust_store()
    analytics = store["analytics"]

    # Meistgenutzte Eintraege berechnen
    access_counts: dict[str, int] = {}
    for log_entry in analytics.get("access_log", []):
        key = log_entry.get("key", "")
        if log_entry.get("action") in ("lookup", "search"):
            access_counts[key] = access_counts.get(key, 0) + 1

    most_accessed = sorted(access_counts.items(), key=lambda x: x[1], reverse=True)[:10]

    # Vertrauenswuerdigste Eintraege
    most_trusted = sorted(
        [
            {"key": k, "trust_score": v["trust_score"], "confirmations": len(v["confirmations"])}
            for k, v in store["entries"].items()
            if not _is_expired(v)
        ],
        key=lambda x: x["trust_score"],
        reverse=True,
    )[:10]

    # Top-Beitragende Agents
    top_agents = sorted(
        [
            {
                "agent_id": agent_id,
                "stores": data["stores"],
                "confirmations": data["confirmations"],
                "lookups": data["lookups"],
                "total_activity": data["stores"] + data["confirmations"] + data["lookups"],
            }
            for agent_id, data in analytics.get("agent_contributions", {}).items()
        ],
        key=lambda x: x["total_activity"],
        reverse=True,
    )[:10]

    # Cache-Effektivitaet berechnen
    total_lookups = analytics.get("total_lookups", 0)
    total_hits = analytics.get("total_hits", 0)
    hit_rate = (total_hits / total_lookups * 100) if total_lookups > 0 else 0

    # Aktive vs. abgelaufene Eintraege zaehlen
    active_entries = sum(1 for v in store["entries"].values() if not _is_expired(v))
    expired_entries = sum(1 for v in store["entries"].values() if _is_expired(v))

    # Trust-Verteilung
    trust_distribution = {"0": 0, "1": 0, "2-3": 0, "4-5": 0, "6+": 0}
    for v in store["entries"].values():
        if _is_expired(v):
            continue
        score = v["trust_score"]
        if score == 0:
            trust_distribution["0"] += 1
        elif score == 1:
            trust_distribution["1"] += 1
        elif score <= 3:
            trust_distribution["2-3"] += 1
        elif score <= 5:
            trust_distribution["4-5"] += 1
        else:
            trust_distribution["6+"] += 1

    # Zeitbasierte Analyse (letzte 24h vs. gesamt)
    now = time.time()
    recent_log = [e for e in analytics.get("access_log", []) if now - e.get("timestamp", 0) < 86400]
    recent_stores = sum(1 for e in recent_log if e.get("action") == "store")
    recent_lookups = sum(1 for e in recent_log if e.get("action") in ("lookup", "search"))
    recent_confirmations = sum(1 for e in recent_log if e.get("action") == "confirm")

    return {
        "overview": {
            "total_lookups": total_lookups,
            "total_hits": total_hits,
            "total_misses": analytics.get("total_misses", 0),
            "total_stores": analytics.get("total_stores", 0),
            "total_confirmations": analytics.get("total_confirmations", 0),
            "hit_rate_percent": round(hit_rate, 1),
            "active_entries": active_entries,
            "expired_entries": expired_entries,
        },
        "last_24h": {
            "stores": recent_stores,
            "lookups": recent_lookups,
            "confirmations": recent_confirmations,
        },
        "most_accessed_entries": [{"key": k, "access_count": c} for k, c in most_accessed],
        "most_trusted_entries": most_trusted,
        "top_contributing_agents": top_agents,
        "trust_distribution": trust_distribution,
        "network_effect_score": _calculate_network_score(store),
    }


def _calculate_network_score(store: dict) -> dict:
    """Berechnet einen Netzwerkeffekt-Score basierend auf Diversitaet und Aktivitaet."""
    unique_agents = len(store["analytics"].get("agent_contributions", {}))
    total_confirmations = store["analytics"].get("total_confirmations", 0)
    active_entries = sum(1 for v in store["entries"].values() if not _is_expired(v))
    avg_trust = 0
    if active_entries > 0:
        total_trust = sum(v["trust_score"] for v in store["entries"].values() if not _is_expired(v))
        avg_trust = round(total_trust / active_entries, 2)

    # Score: 0-100, basierend auf Agenten-Diversitaet, Confirmations und aktiven Eintraegen
    score = min(100, (unique_agents * 10) + (total_confirmations * 2) + (active_entries * 1))

    return {
        "score": score,
        "unique_agents": unique_agents,
        "avg_trust_score": avg_trust,
        "interpretation": (
            "strong" if score >= 70
            else "growing" if score >= 30
            else "early stage"
        ),
    }


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
        data = resp.json()

    # Trust-Daten an Eintraege anhaengen
    store = _load_trust_store()
    entries = data.get("entries", [])
    for entry in entries:
        key = entry.get("key", "")
        entry_trust = _get_entry_trust(store, key)
        entry["trust_score"] = entry_trust.get("trust_score", 0)
        entry["confirmation_count"] = len(entry_trust.get("confirmations", []))
        if _is_expired(entry_trust):
            entry["expired"] = True

    # Abgelaufene rausfiltern
    data["entries"] = [e for e in entries if not e.get("expired")]
    return data

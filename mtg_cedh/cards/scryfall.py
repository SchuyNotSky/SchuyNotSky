"""
Scryfall API integration.

Fetches real card data from https://api.scryfall.com and caches results
in a local JSON file so we don't hammer the API on every run.

Scryfall's terms of service ask for a small delay between requests (50–100 ms),
which we respect via RATE_LIMIT_DELAY.

Usage:
    from mtg_cedh.cards.scryfall import get_card, bulk_fetch
    data = get_card("Sol Ring")          # returns raw Scryfall JSON dict
    cards = bulk_fetch(["Sol Ring", "Counterspell"])
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Dict, List, Optional

import requests

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

SCRYFALL_BASE = "https://api.scryfall.com"
CACHE_PATH = Path(__file__).parent / "scryfall_cache.json"
RATE_LIMIT_DELAY = 0.1   # 100 ms between requests per Scryfall ToS


# ---------------------------------------------------------------------------
# Cache helpers
# ---------------------------------------------------------------------------

def _load_cache() -> Dict[str, dict]:
    if CACHE_PATH.exists():
        try:
            return json.loads(CACHE_PATH.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def _save_cache(cache: Dict[str, dict]):
    CACHE_PATH.write_text(
        json.dumps(cache, indent=2, ensure_ascii=False), encoding="utf-8"
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_card(name: str, use_cache: bool = True) -> Optional[dict]:
    """
    Fetch a single card by exact name from Scryfall.
    Returns the raw Scryfall card JSON dict, or None on failure.
    Results are cached to disk.
    """
    cache = _load_cache()
    key = name.lower().strip()

    if use_cache and key in cache:
        return cache[key]

    try:
        resp = requests.get(
            f"{SCRYFALL_BASE}/cards/named",
            params={"exact": name},
            timeout=10,
        )
        time.sleep(RATE_LIMIT_DELAY)

        if resp.status_code == 200:
            data = resp.json()
            cache[key] = data
            _save_cache(cache)
            return data
        else:
            print(f"[Scryfall] Card not found: {name!r}  (HTTP {resp.status_code})")
            return None

    except requests.RequestException as exc:
        print(f"[Scryfall] Network error fetching {name!r}: {exc}")
        return None


def bulk_fetch(names: List[str], use_cache: bool = True) -> Dict[str, dict]:
    """
    Fetch multiple cards by name.
    Returns dict mapping lowercase name -> Scryfall JSON.
    Already-cached cards are served from cache without hitting the network.
    """
    cache = _load_cache()
    result: Dict[str, dict] = {}
    to_fetch: List[str] = []

    for name in names:
        key = name.lower().strip()
        if use_cache and key in cache:
            result[key] = cache[key]
        else:
            to_fetch.append(name)

    if to_fetch:
        print(f"[Scryfall] Fetching {len(to_fetch)} cards from API …")
        for name in to_fetch:
            key = name.lower().strip()
            data = get_card(name, use_cache=False)
            if data:
                result[key] = data
                cache[key] = data
        _save_cache(cache)
        print(f"[Scryfall] Done. Cache now has {len(cache)} entries.")

    return result


def search_cards(query: str, max_results: int = 20) -> List[dict]:
    """
    Search Scryfall with a full-text query (Scryfall syntax supported).
    e.g. search_cards("c:u t:instant o:counter")
    """
    results = []
    url = f"{SCRYFALL_BASE}/cards/search"
    params = {"q": query, "order": "edhrec"}

    while url and len(results) < max_results:
        try:
            resp = requests.get(url, params=params, timeout=10)
            time.sleep(RATE_LIMIT_DELAY)
            if resp.status_code != 200:
                break
            page = resp.json()
            results.extend(page.get("data", []))
            url = page.get("next_page")
            params = {}  # next_page already has params
        except requests.RequestException:
            break

    return results[:max_results]


def prefetch_cedh_staples():
    """
    Pre-populate the cache with all cEDH staple cards.
    Call this once to seed the cache; subsequent runs will be instant.
    """
    from .database import CEDH_STAPLE_NAMES
    print(f"[Scryfall] Pre-fetching {len(CEDH_STAPLE_NAMES)} cEDH staples …")
    bulk_fetch(CEDH_STAPLE_NAMES)
    print("[Scryfall] Pre-fetch complete.")

"""Read episode orders from TheTVDB v4."""

from functools import lru_cache

import requests

BASE_URL = "https://api4.thetvdb.com/v4"
ORDERS = ("official", "dvd", "alternate", "absolute", "regional", "altdvd", "alttwo")


@lru_cache(maxsize=4)
def _token(key, pin):
    data = {"apikey": key}
    if pin:
        data["pin"] = pin
    response = requests.post(f"{BASE_URL}/login", json=data, timeout=5)
    response.raise_for_status()
    return response.json()["data"]["token"]


@lru_cache(maxsize=128)
def season_episodes(series_id, order, season, key, pin):
    episodes = []
    page = 0
    refreshed = False
    while True:
        response = requests.get(
            f"{BASE_URL}/series/{series_id}/episodes/{order}",
            params={"season": season, "page": page},
            headers={"Authorization": f"Bearer {_token(key, pin)}"}, timeout=5,
        )
        if response.status_code == 401 and not refreshed:
            _token.cache_clear()
            refreshed = True
            continue
        if response.status_code == 404:
            return tuple(episodes)
        response.raise_for_status()
        data = response.json()
        episodes.extend((data.get("data") or {}).get("episodes") or [])
        if not (data.get("links") or {}).get("next"):
            return tuple(episodes)
        page += 1

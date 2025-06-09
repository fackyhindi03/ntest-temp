# hianimez_scraper.py

import os
import re
import json
import requests
from bs4 import BeautifulSoup

ANIWATCH_API_BASE = os.getenv(
    "ANIWATCH_API_BASE",
    "http://localhost:4000/api/v2/hianime"
)


def search_anime(query: str):
    """
    Uses the aniwatch-API to search for anime.
    Returns a list of (title, anime_url, slug).
    """
    url = f"{ANIWATCH_API_BASE}/search"
    params = {"q": query, "page": 1}
    resp = requests.get(url, params=params, timeout=10)
    resp.raise_for_status()

    animes = resp.json().get("data", {}).get("animes", [])
    results = []
    for item in animes:
        if isinstance(item, str):
            slug = item
            title = slug.replace("-", " ").title()
        else:
            slug = item.get("id", "")
            title = item.get("name") or item.get("jname") or slug.replace("-", " ").title()
        if slug:
            results.append((title, f"https://hianimez.to/watch/{slug}", slug))
    return results


def get_episodes_list(slug: str):
    """
    Uses the aniwatch-API to list episodes.
    Returns a list of (episode_number, episode_id) tuples.
    """
    url = f"{ANIWATCH_API_BASE}/anime/{slug}/episodes"
    resp = requests.get(url, timeout=10)
    if resp.status_code == 404:
        return [("1", f"{slug}?ep=1")]
    resp.raise_for_status()

    eps = resp.json().get("data", {}).get("episodes", [])
    episodes = []
    for e in eps:
        num = str(e.get("number", "")).strip()
        eid = e.get("episodeId", "").strip()
        if num and eid:
            episodes.append((num, eid))
    episodes.sort(key=lambda x: int(x[0]))
    return episodes


def extract_episode_stream_and_subtitle(episode_id: str):
    """
    Directly scrape hianime.to to get the .m3u8 stream and English subtitle.
    episode_id looks like "naruto-1?ep=1".
    """
    # 1) Split slug & ep number
    slug, _, epnum = episode_id.partition("?ep=")

    # 2) Fetch the episode page
    url = f"https://hianime.to/watch/{slug}-{epnum}"
    headers = {"User-Agent": "Mozilla/5.0"}
    resp = requests.get(url, headers=headers, timeout=10)
    resp.raise_for_status()
    html = resp.text

    # 3) Extract the embedded Nuxt JSON
    m = re.search(r"window\.__NUXT__=(\{.*?\});", html)
    if not m:
        raise RuntimeError("Embedded JSON payload not found on page")
    payload = json.loads(m.group(1))

    # 4) Find the right episode object
    episodes = payload.get("data", {}).get("episodes", [])
    ep_obj = next((e for e in episodes if str(e.get("number")) == epnum), None)
    if not ep_obj:
        raise RuntimeError(f"Episode {epnum} not in page payload")

    # 5) Pull the HLS stream URL
    hls_link = next(
        (s.get("url") for s in ep_obj.get("sources", [])
         if s.get("type") == "hls" and s.get("url")),
        None
    )

    # 6) Pull the English subtitle URL
    subtitle_url = None
    for tr in ep_obj.get("tracks", []):
        lang = tr.get("lang", "") or tr.get("label", "")
        if lang.lower().startswith("english") and tr.get("url"):
            subtitle_url = tr["url"]
            break

    return hls_link, subtitle_url

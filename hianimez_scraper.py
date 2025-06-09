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


def extract_episode_stream_and_subtitle(slug: str, ep_num: str):
    """
    Scrape hianime.to/watch/{slug}?ep={ep_num} for the HLS URL and English VTT.
    """
    page_url = f"https://hianime.to/watch/{slug}?ep={ep_num}"
    headers = {"User-Agent": "Mozilla/5.0"}
    resp = requests.get(page_url, headers=headers, timeout=10)
    resp.raise_for_status()
    html = resp.text

    # 1) Try window.__NUXT__ inline JSON
    m = re.search(r"window\.__NUXT__\s*=\s*(\{.*?\});", html, re.DOTALL)
    if m:
        raw = m.group(1)

    else:
        # 2) Try the Nuxt <script id="__NUXT_DATA__"> JSON blob
        m = re.search(
            r'<script[^>]+id="__NUXT_DATA__"[^>]*>\s*({.*?})\s*</script>',
            html, re.DOTALL
        )
        if m:
            raw = m.group(1)
        else:
            # 3) Finally, try the Next.js <script id="__NEXT_DATA__"> blob
            m = re.search(
                r'<script[^>]+id="__NEXT_DATA__"[^>]*>\s*({.*?})\s*</script>',
                html, re.DOTALL
            )
            if not m:
                raise RuntimeError("Could not find embedded JSON on page")
            raw = m.group(1)

    # Parse the JSON we found:
    payload = json.loads(raw)

    # 3) Locate the current episode in payload
    episodes = payload.get("data", {}).get("episodes", [])
    ep_obj = next((e for e in episodes if str(e.get("number")) == ep_num), None)
    if not ep_obj:
        raise RuntimeError(f"Episode {ep_num} not found in page payload")

    # 4) Extract the HLS stream
    hls_link = next(
        (src["url"] for src in ep_obj.get("sources", [])
         if src.get("type") == "hls" and src.get("url")),
        None
    )

    # 5) Extract the English subtitle
    subtitle_url = None
    for tr in ep_obj.get("tracks", []):
        lang = tr.get("lang", "") or tr.get("label", "")
        if lang.lower().startswith("english") and tr.get("url"):
            subtitle_url = tr["url"]
            break

    return hls_link, subtitle_url

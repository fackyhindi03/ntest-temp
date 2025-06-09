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
    Scrape hianime.to/watch/{slug}?ep={ep_num} for the HLS URL and English subtitles.
    Tries:
      1) window.__NUXT__ inline JSON
      2) <script id="__NUXT_DATA__"> JSON blob
      3) <script id="__NEXT_DATA__"> JSON blob
      4) FALLBACK: regex scan for .m3u8 and .vtt/.srt in HTML
    """
    page_url = f"https://hianime.to/watch/{slug}?ep={ep_num}"
    headers = {"User-Agent": "Mozilla/5.0"}
    resp = requests.get(page_url, headers=headers, timeout=10)
    resp.raise_for_status()
    html = resp.text

    # 1) Inline Nuxt state
    m = re.search(r"window\.__NUXT__\s*=\s*(\{.*?\});", html, re.DOTALL)
    raw = None
    if m:
        raw = m.group(1)
    else:
        # 2) Nuxt data tag
        m = re.search(
            r'<script[^>]+id="__NUXT_DATA__"[^>]*>\s*(\{.*?\})\s*</script>',
            html, re.DOTALL
        )
        if m:
            raw = m.group(1)
        else:
            # 3) Next.js data tag
            m = re.search(
                r'<script[^>]+id="__NEXT_DATA__"[^>]*>\s*(\{.*?\})\s*</script>',
                html, re.DOTALL
            )
            if m:
                raw = m.group(1)

    if raw:
        data = json.loads(raw).get("data", {})
        ep_obj = next((e for e in data.get("episodes", [])
                       if str(e.get("number")) == ep_num), None)
        if ep_obj:
            # pull JSON sources
            hls = next((s["url"] for s in ep_obj.get("sources", [])
                        if s.get("type") == "hls" and s.get("url")), None)
            # pull JSON subtitles
            subtitle = None
            for tr in ep_obj.get("tracks", []):
                lang = tr.get("lang","") or tr.get("label","")
                if lang.lower().startswith("english") and tr.get("url"):
                    subtitle = tr["url"]
                    break
            return hls, subtitle

    # 4) FALLBACK: regex scan for any .m3u8 and subtitle links in the HTML
    hls_match = re.search(r"https?://[^'\"\s]+\.m3u8[^'\"\s]*", html)
    sub_match = re.search(r"https?://[^'\"\s]+\.(?:vtt|srt)[^'\"\s]*", html)

    hls = hls_match.group(0) if hls_match else None
    subtitle = sub_match.group(0) if sub_match else None
    return hls, subtitle

# hianimez_scraper.py

import os
import requests
import logging
from typing import Tuple, Optional

logger = logging.getLogger(__name__)
ANIWATCH_API_BASE = os.getenv(
    "ANIWATCH_API_BASE",
    "http://localhost:4000/api/v2/hianime"
)


def search_anime(query: str):
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
    url = f"{ANIWATCH_API_BASE}/anime/{slug}/episodes"
    resp = requests.get(url, timeout=10)
    if resp.status_code == 404:
        return [("1", f"{slug}?ep=1")]
    resp.raise_for_status()
    eps = resp.json().get("data", {}).get("episodes", [])
    out = []
    for e in eps:
        num = str(e.get("number", "")).strip()
        eid = e.get("episodeId", "").strip()
        if num and eid:
            out.append((num, eid))
    out.sort(key=lambda x: int(x[0]))
    return out


def extract_episode_stream_and_subtitle(episode_id: str):
    """
    1) GET the watch page for the given episode_id, e.g. "raven-of-the-inner-palace-18168?ep=94361"
    2) Regex out the full https://niwinn.com/sbar.json?... URL
    3) Unescape any HTML entities (&amp; → &), then GET it with the correct Referer
    4) Parse JSON for the .m3u8 and .vtt/.srt links
    """
    page_url = f"https://hianime.pe/watch/{episode_id}"
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Referer": page_url
    }

    # 1) fetch the episode page
    r = requests.get(page_url, headers=headers, timeout=10)
    r.raise_for_status()
    html = r.text

    # 2) find the full niwinn URL
    m = re.search(r'(https://niwinn\.com/sbar\.json\?[^"\']+)', html)
    if not m:
        logger.error("Could not find niwinn URL in page HTML")
        return None, None

    sbar_url = m.group(1).replace("&amp;", "&")

    # 3) fetch the niwinn JSON
    r2 = requests.get(sbar_url, headers=headers, timeout=10)
    r2.raise_for_status()
    data = r2.json()
    logger.debug("niwinn JSON: %s", data)

    # 4) locate your video+subtitle entries
    #    Adjust these keys to match the actual JSON shape you see in your logs!
    #    Common fields are "video" or "playlist" or "sources"
    video_list = data.get("video") or data.get("playlist") or data.get("sources") or []
    if not video_list:
        logger.error("No video entries in sbar.json response")
        return None, None

    # pick the first .m3u8
    hls_link = next(
        (item.get("file") for item in video_list
         if item.get("file", "").endswith(".m3u8")),
        None
    )

    # pick the first subtitle track
    subtitle_url = next(
        (item.get("subtitle") or item.get("captions") or item.get("file")
         for item in video_list
         if (item.get("subtitle","") or "").endswith((".vtt", ".srt"))),
        None
    )

    return hls_link, subtitle_url

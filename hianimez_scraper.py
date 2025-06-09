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


def extract_episode_stream_and_subtitle(episode_id: str) -> Tuple[Optional[str], Optional[str]]:
    """
    1) GET /episode/servers to list all sub/dub/raw servers.
    2) Try each server (sub first, then raw, then dub) by calling
       /episode/sources?animeEpisodeId=…&server=… 
    3) The first non‐empty sources array wins.
    4) Pick the first HLS URL and the first English track from that.
    """
    # 1) fetch the list of servers
    srv_url = f"{ANIWATCH_API_BASE}/episode/servers"
    r = requests.get(srv_url, params={"animeEpisodeId": episode_id}, timeout=10)
    r.raise_for_status()
    data = r.json().get("data", {})
    # try sub, then raw, then dub
    for category in ("sub", "raw", "dub"):
        servers = data.get(category, [])
        for s in servers:
            server_name = s.get("serverName") or s.get("name")
            if not server_name:
                continue

            # 2) fetch sources from that server
            src_url = f"{ANIWATCH_API_BASE}/episode/sources"
            r2 = requests.get(
                src_url,
                params={
                    "animeEpisodeId": episode_id,
                    "server":         server_name,
                },
                timeout=10
            )
            if not r2.ok:
                continue

            d2 = r2.json().get("data", {})
            sources  = d2.get("sources", [])
            tracks   = d2.get("tracks", []) + d2.get("subtitles", [])

            if not sources:
                continue

            # 3) extract the HLS link
            hls_link = next(
                (s["url"] for s in sources 
                 if s.get("type") == "hls" and s.get("url")),
                None
            )

            # 4) extract the English subtitle
            subtitle = next(
                (t.get("file") or t.get("url") for t in tracks
                 if (t.get("label","") or t.get("lang","")).lower().startswith("english")
                ),
                None
            )

            logger.info("Got stream from server '%s': %s", server_name, hls_link)
            return hls_link, subtitle

    # if we fall through, nothing worked
    logger.warning("No servers yielded a stream for %s", episode_id)
    return None, None

# hianimez_scraper.py

import os
import asyncio
from typing import Tuple, Optional
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeout
import logging

logger = logging.getLogger(__name__)

ANIWATCH_API_BASE = os.getenv(
    "ANIWATCH_API_BASE",
    "http://localhost:4000/api/v2/hianime"
)

# ———————————————————————————————————————————————
# (1) Search & episodes-list still via the API:
# ———————————————————————————————————————————————

import requests

def search_anime(query: str):
    url = f"{ANIWATCH_API_BASE}/search"
    params = {"q": query, "page": 1}
    r = requests.get(url, params=params, timeout=10)
    r.raise_for_status()
    animes = r.json().get("data", {}).get("animes", [])
    results = []
    for item in animes:
        if isinstance(item, str):
            slug = item
            title = slug.replace("-", " ").title()
        else:
            slug = item.get("id","")
            title = item.get("name") or item.get("jname") or slug.replace("-", " ").title()
        if slug:
            results.append((title, f"https://hianimez.to/watch/{slug}", slug))
    return results

def get_episodes_list(slug: str):
    url = f"{ANIWATCH_API_BASE}/anime/{slug}/episodes"
    r = requests.get(url, timeout=10)
    if r.status_code == 404:
        return [("1", f"{slug}?ep=1")]
    r.raise_for_status()
    eps = r.json().get("data", {}).get("episodes", [])
    episodes = []
    for e in eps:
        num = str(e.get("number","")).strip()
        eid = e.get("episodeId","").strip()
        if num and eid:
            episodes.append((num, eid))
    episodes.sort(key=lambda x:int(x[0]))
    return episodes

# ———————————————————————————————————————————————
# (2) Dynamic Playwright scraper:
# ———————————————————————————————————————————————

async def _fetch_with_playwright(slug: str, ep_num: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Launch a headless browser, navigate to the episode page,
    and listen for any .m3u8 or subtitle responses.
    """
    url = f"https://hianime.to/watch/{slug}?ep={ep_num}"
    logger.info("▶️ Loading %s …", url)

    m3u8_url = None
    sub_url  = None

    try:
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True)
            page = await browser.new_page(user_agent="Mozilla/5.0")
            # intercept responses
            page.on("response", lambda resp: _sniff(resp, lambda u, s: (u, s), 
                                                   setter=lambda u,s: (nonlocal_set("m3u8", u), nonlocal_set("sub", s))))
            # navigate
            await page.goto(url, wait_until="networkidle", timeout=15000)
            # give it a couple seconds to fire off playlist loads
            await page.wait_for_timeout(3000)
            await browser.close()
    except PlaywrightTimeout:
        logger.warning("⏱️ Playwright timeout for %s ep%s", slug, ep_num)
    except Exception as e:
        logger.error("❌ Playwright error: %s", e)

    return m3u8_url, sub_url

# Helpers to let lambda set outer-scope vars:
def nonlocal_set(name, value):
    globals()[name] = value  # quick hack; m3u8 and sub become globals

def _sniff(response, ignore, setter):
    url = response.url
    if ".m3u8" in url and not globals().get("m3u8"):
        setter(url, None)
    if url.endswith(".vtt") and not globals().get("sub"):
        setter(None, url)

def extract_episode_stream_and_subtitle(slug: str, ep_num: str):
    """
    Sync wrapper around the async headless‐browser fetch.
    Uses asyncio.run so we always get a fresh loop.
    """
    return asyncio.run(_fetch_with_playwright(slug, ep_num))


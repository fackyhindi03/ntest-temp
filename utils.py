# utils.py

import os
import requests

def download_and_rename_subtitle(subtitle_url, episode_num, cache_dir="subtitles_cache"):
    """
    Download a .vtt subtitle and save it as episode_{n}.vtt in cache_dir.
    Returns the local file path.
    """
    if not subtitle_url:
        raise ValueError("No subtitle URL provided")

    os.makedirs(cache_dir, exist_ok=True)
    local_filename = os.path.join(cache_dir, f"episode_{episode_num}.vtt")

    resp = requests.get(subtitle_url, timeout=10)
    resp.raise_for_status()
    with open(local_filename, "wb") as f:
        f.write(resp.content)

    return local_filename

"""
LUCIA YouTube Tools - Ultra Fast & Instant Window Pop-up
"""
import os
import subprocess
import webbrowser
import urllib.parse
import re
import threading

def clean_youtube_query(query: str) -> str:
    q = query.lower()
    fillers = [
        "youtube per", "youtube par", "youtube pe", "youtube", 
        "chalao", "play", "lagao", "sunao", "kholo", "open", "video", "song"
    ]
    for f in fillers:
        q = q.replace(f, " ")
    return re.sub(r'\s+', ' ', q).strip()


def launch_browser_async(url: str):
    """Launches browser in a non-blocking background thread for 0-latency window opening"""
    def _open():
        try:
            # 1. Direct Linux Desktop GUI launcher
            subprocess.Popen(
                ["xdg-open", url],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                env=os.environ.copy()
            )
        except Exception:
            webbrowser.open(url)
            
    threading.Thread(target=_open, daemon=True).start()


def play_youtube(query: str) -> dict:
    clean_query = clean_youtube_query(query)
    if not clean_query:
        clean_query = query.strip()
        
    print(f"⚡ Instant resolving & launching video: '{clean_query}'...")

    # Fast DDGS Video Search
    try:
        from duckduckgo_search import DDGS
        with DDGS() as ddgs:
            results = list(ddgs.videos(clean_query, max_results=2))
            for item in results:
                v_url = item.get("content") or item.get("url") or ""
                v_title = item.get("title", clean_query)
                
                if "youtube.com/watch" in v_url or "youtu.be/" in v_url:
                    launch_browser_async(v_url)
                    return {
                        "success": True, 
                        "message": f"YouTube par '{v_title}' play kar diya hai!"
                    }
    except Exception as e:
        print(f"[Fast Search Warning]: {e}")

    # Instant Fallback to Direct YouTube Query
    fallback_url = f"https://www.youtube.com/results?search_query={urllib.parse.quote(clean_query)}"
    launch_browser_async(fallback_url)
    return {
        "success": True, 
        "message": f"YouTube par '{clean_query}' khol diya hai."
    }


def search_youtube(query: str) -> dict:
    clean_query = clean_youtube_query(query)
    if not clean_query:
        clean_query = query.strip()
    url = f"https://www.youtube.com/results?search_query={urllib.parse.quote(clean_query)}"
    launch_browser_async(url)
    return {"success": True, "message": f"YouTube par '{clean_query}' search kar diya."}
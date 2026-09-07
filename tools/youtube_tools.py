"""
LUCIA YouTube Tools
- Clean Query Extraction
- Direct Video Launcher via YouTube initialData JSON Parser
"""
import urllib.parse
import urllib.request
import re
from tools.browser_tools import launch_browser_async


def clean_youtube_query(query: str) -> str:
    """Removes filler words like 'youtube per', 'chalao', 'lagao' from search"""
    q = query.lower()
    fillers = [
        "youtube per", "youtube par", "youtube pe", "youtube", 
        "chalao", "play", "lagao", "sunao", "kholo", "open", "video", "song"
    ]
    for f in fillers:
        q = q.replace(f, " ")
    return re.sub(r'\s+', ' ', q).strip()


def play_youtube(query: str) -> dict:
    clean_query = clean_youtube_query(query)
    if not clean_query:
        clean_query = query.strip()
        
    print(f"🎬 Resolving top video directly from YouTube for: '{clean_query}'...")

    try:
        encoded_query = urllib.parse.quote_plus(clean_query)
        search_url = f"https://www.youtube.com/results?search_query={encoded_query}"
        
        req = urllib.request.Request(
            search_url,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            }
        )
        
        with urllib.request.urlopen(req, timeout=5) as response:
            html = response.read().decode('utf-8', errors='ignore')
        
        video_ids = re.findall(r'"videoId":"([a-zA-Z0-9_-]{11})"', html)
        
        valid_ids = []
        for vid in video_ids:
            if vid not in valid_ids and len(vid) == 11:
                valid_ids.append(vid)
                
        if valid_ids:
            top_video_url = f"https://www.youtube.com/watch?v={valid_ids[0]}"
            print(f"▶ Launching top video: {top_video_url}")
            launch_browser_async(top_video_url)
            return {
                "success": True, 
                "message": f"YouTube par '{clean_query}' play kar diya hai!"
            }
            
    except Exception as e:
        print(f"[YouTube Direct Resolver Warning]: {e}")

    fallback_url = f"https://www.youtube.com/results?search_query={urllib.parse.quote(clean_query)}"
    launch_browser_async(fallback_url)
    return {
        "success": True, 
        "message": f"YouTube par '{clean_query}' search results khol diye hain."
    }


def search_youtube(query: str) -> dict:
    clean_query = clean_youtube_query(query)
    if not clean_query:
        clean_query = query.strip()
    try:
        url = f"https://www.youtube.com/results?search_query={urllib.parse.quote(clean_query)}"
        launch_browser_async(url)
        return {"success": True, "message": f"YouTube par '{clean_query}' search kar diya."}
    except Exception as e:
        return {"success": False, "message": f"YouTube search nahi hui: {e}"}
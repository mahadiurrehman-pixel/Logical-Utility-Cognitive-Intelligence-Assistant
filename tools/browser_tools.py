"""
LUCIA Universal Browser Tools
- Asynchronous desktop-safe background launcher
- Opens any website, URL, Google search, or web apps
"""
import os
import subprocess
import webbrowser
import urllib.parse
import re
import threading

POPULAR_SITES = {
    "github": "https://github.com",
    "chatgpt": "https://chatgpt.com",
    "claude": "https://claude.ai",
    "gemini": "https://gemini.google.com",
    "netflix": "https://netflix.com",
    "linkedin": "https://linkedin.com",
    "twitter": "https://x.com",
    "x": "https://x.com",
    "reddit": "https://reddit.com",
    "spotify": "https://open.spotify.com",
    "stackoverflow": "https://stackoverflow.com",
    "stack overflow": "https://stackoverflow.com",
    "gmail": "https://mail.google.com",
    "google": "https://google.com",
    "youtube": "https://youtube.com",
    "facebook": "https://facebook.com",
    "instagram": "https://instagram.com",
    "whatsapp": "https://web.whatsapp.com",
    "amazon": "https://amazon.com",
    "notion": "https://notion.so",
    "canva": "https://canva.com",
    "medium": "https://medium.com",
    "discord": "https://discord.com/app",
    "kaggle": "https://kaggle.com",
    "huggingface": "https://huggingface.co",
    "hugging face": "https://huggingface.co"
}


def launch_browser_async(url: str):
    """
    ⚡ Launches browser in a non-blocking background thread.
    Bypasses Linux systemd GUI permission blocks via xdg-open.
    """
    def _open():
        try:
            # 1. Direct Linux Desktop GUI launcher (systemd-safe)
            subprocess.Popen(
                ["xdg-open", url],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                env=os.environ.copy()
            )
        except Exception:
            # 2. Fallback to standard Python webbrowser
            webbrowser.open(url)
            
    threading.Thread(target=_open, daemon=True).start()


def open_website(url: str) -> dict:
    """Opens ANY website, web app or URL in the default browser"""
    try:
        raw_target = url.strip()
        clean_name = raw_target.lower().replace("www.", "").replace("https://", "").replace("http://", "").strip("/")
        
        # 1. Check popular shortcuts
        if clean_name in POPULAR_SITES:
            final_url = POPULAR_SITES[clean_name]
        elif clean_name.replace(" ", "") in POPULAR_SITES:
            final_url = POPULAR_SITES[clean_name.replace(" ", "")]
        else:
            # 2. Build full URL
            if not raw_target.startswith("http://") and not raw_target.startswith("https://"):
                if "." not in raw_target:
                    final_url = f"https://www.{raw_target}.com"
                else:
                    final_url = f"https://{raw_target}"
            else:
                final_url = raw_target

        launch_browser_async(final_url)
        return {"success": True, "message": f"{final_url} khol diya."}
    except Exception as e:
        return {"success": False, "message": f"Website nahi khul saki: {e}"}


def open_google(query: str = "") -> dict:
    """Opens Google search or homepage"""
    try:
        if query:
            url = f"https://www.google.com/search?q={urllib.parse.quote(query)}"
            launch_browser_async(url)
            return {"success": True, "message": f"Google par '{query}' search kar diya."}
        
        launch_browser_async("https://www.google.com")
        return {"success": True, "message": "Google khol diya."}
    except Exception as e:
        return {"success": False, "message": f"Google nahi khul saka: {e}"}


def open_youtube() -> dict:
    """Opens YouTube homepage"""
    try:
        launch_browser_async("https://www.youtube.com")
        return {"success": True, "message": "YouTube khol diya."}
    except Exception as e:
        return {"success": False, "message": f"YouTube nahi khul saka: {e}"}
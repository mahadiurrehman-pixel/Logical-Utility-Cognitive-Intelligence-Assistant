import webbrowser
import urllib.parse
import re

# Popular websites direct mapping for fast and accurate launch
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


def open_website(url: str) -> dict:
    """
    Opens ANY website or web application in the default browser.
    Handles names ('github', 'netflix'), domains ('cricbuzz.com'), and full URLs.
    """
    try:
        raw_target = url.strip()
        clean_name = raw_target.lower().replace("www.", "").replace("https://", "").replace("http://", "").strip("/")
        
        # 1. Check direct popular shortcuts
        if clean_name in POPULAR_SITES:
            final_url = POPULAR_SITES[clean_name]
        elif clean_name.replace(" ", "") in POPULAR_SITES:
            final_url = POPULAR_SITES[clean_name.replace(" ", "")]
        else:
            # 2. General URL builder
            if not raw_target.startswith("http://") and not raw_target.startswith("https://"):
                if "." not in raw_target:
                    # Agar user ne sirf 'daraz' ya 'coursera' bola ho
                    final_url = f"https://www.{raw_target}.com"
                else:
                    final_url = f"https://{raw_target}"
            else:
                final_url = raw_target

        webbrowser.open(final_url)
        return {"success": True, "message": f"{final_url} khol diya."}
    except Exception as e:
        return {"success": False, "message": f"Website nahi khul saki: {e}"}


def open_google(query: str = "") -> dict:
    """Opens Google search or homepage"""
    try:
        if query:
            url = f"https://www.google.com/search?q={urllib.parse.quote(query)}"
            webbrowser.open(url)
            return {"success": True, "message": f"Google par '{query}' search kar diya."}
        webbrowser.open("https://www.google.com")
        return {"success": True, "message": "Google khol diya."}
    except Exception as e:
        return {"success": False, "message": f"Google nahi khul saka: {e}"}


def open_youtube() -> dict:
    """Opens YouTube homepage"""
    try:
        webbrowser.open("https://www.youtube.com")
        return {"success": True, "message": "YouTube khol diya."}
    except Exception as e:
        return {"success": False, "message": f"YouTube nahi khul saka: {e}"}
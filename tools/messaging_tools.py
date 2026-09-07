"""
LUCIA's Messaging & Social Tools
- Desktop-safe asynchronous browser launch
- Instant WhatsApp & Instagram messaging and search
"""
import json
import os
import uuid
import urllib.parse
from tools.browser_tools import launch_browser_async

CONTACTS_FILE = "contacts.json"

def load_contacts():
    if not os.path.exists(CONTACTS_FILE):
        default_contacts = {
            "whatsapp": {
                "ali": "+923001234567",
                "sara": "+923009876543"
            },
            "instagram": {
                "ali": "ali_official_ig",
                "sara": "sara_designs"
            }
        }
        with open(CONTACTS_FILE, "w", encoding="utf-8") as f:
            json.dump(default_contacts, f, indent=4)
        return default_contacts
        
    try:
        with open(CONTACTS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"whatsapp": {}, "instagram": {}}


def find_contact(platform: str, name: str):
    """Fuzzy match contact by name in contacts.json"""
    contacts = load_contacts()
    platform_contacts = contacts.get(platform.lower(), {})
    
    name_lower = name.lower().strip().replace("@", "")
    
    if name_lower in platform_contacts:
        return platform_contacts[name_lower]
    
    for saved_name, contact_id in platform_contacts.items():
        if name_lower in saved_name.lower() or saved_name.lower() in name_lower:
            return contact_id
    
    if platform.lower() == "whatsapp" and (name.startswith("+") or name.isdigit()):
        return name
        
    return None


# ==========================================
# 🔍 SEARCH INSTAGRAM (Background Safe)
# ==========================================
def search_instagram(query: str) -> dict:
    try:
        clean_query = query.strip()
        
        if clean_query.startswith("@"):
            username = clean_query[1:].strip()
            url = f"https://www.instagram.com/{username}/"
            msg = f"Instagram par '@{username}' ki profile khol di."
        elif clean_query.startswith("#"):
            tag = clean_query[1:].strip()
            url = f"https://www.instagram.com/explore/tags/{urllib.parse.quote(tag)}/"
            msg = f"Instagram par hashtag '#{tag}' search kar diya."
        else:
            saved_username = find_contact("instagram", clean_query)
            if saved_username:
                url = f"https://www.instagram.com/{saved_username}/"
                msg = f"Instagram par {clean_query} (@{saved_username}) ki profile khol di."
            else:
                encoded = urllib.parse.quote(clean_query)
                url = f"https://www.instagram.com/explore/search/keyword/?q={encoded}"
                msg = f"Instagram par '{clean_query}' search kar diya."
                
        launch_browser_async(url)
        return {"success": True, "message": msg}
    except Exception as e:
        return {"success": False, "message": f"Instagram search nahi ho saki: {e}"}


# ==========================================
# 🔍 SEARCH WHATSAPP (Background Safe)
# ==========================================
def search_whatsapp(query: str) -> dict:
    try:
        clean_query = query.strip()
        contact_id = find_contact("whatsapp", clean_query)
        
        if contact_id:
            clean_phone = str(contact_id).replace(" ", "").replace("-", "")
            if not clean_phone.startswith("+"):
                if clean_phone.startswith("0"):
                    clean_phone = "+92" + clean_phone[1:]
                else:
                    clean_phone = "+92" + clean_phone
                    
            url = f"https://web.whatsapp.com/send?phone={clean_phone}"
            launch_browser_async(url)
            return {
                "success": True, 
                "message": f"WhatsApp par {clean_query} ({clean_phone}) ki chat khol di."
            }
        
        launch_browser_async("https://web.whatsapp.com")
        hint = ""
        try:
            import pyperclip
            pyperclip.copy(clean_query)
            hint = f"'{clean_query}' search bar ke liye copy kar diya hai, bas paste kar lein."
        except Exception:
            hint = f"WhatsApp Web par '{clean_query}' dhoond lein."
            
        return {
            "success": True, 
            "message": f"WhatsApp Web khol diya hai. {hint}"
        }
    except Exception as e:
        return {"success": False, "message": f"WhatsApp search fail: {e}"}


# ==========================================
# 📩 DRAFT & SEND MESSAGES (Background Safe)
# ==========================================
def draft_message(platform: str, contact: str, message: str) -> dict:
    platform = platform.lower().strip()
    
    if platform not in ["whatsapp", "instagram"]:
        return {
            "success": False, 
            "message": f"'{platform}' supported nahi hai. Sirf WhatsApp aur Instagram supported hain."
        }
    
    if not message or not message.strip():
        return {"success": False, "message": "Message empty hai."}
    
    if not contact or not contact.strip():
        return {"success": False, "message": "Contact ka naam batao."}
    
    contact_id = find_contact(platform, contact)
    
    # If contact not found, we use contact name as fallback ID directly to avoid deadends
    if not contact_id:
        contact_id = contact
    
    draft = {
        "id": str(uuid.uuid4())[:8],
        "platform": platform,
        "contact_name": contact,
        "contact_id": contact_id,
        "message": message.strip(),
        "status": "pending_confirmation"
    }
    
    return {
        "success": True,
        "message": f"Draft ready hai {platform.title()} par {contact.title()} ke liye.",
        "draft": draft
    }


def send_whatsapp_message(phone: str, message: str) -> dict:
    """⚡ Standardized Background Safe WhatsApp Redirect Launcher"""
    try:
        clean_phone = str(phone).replace(" ", "").replace("-", "")
        # If it's a name (not a number) because contact wasn't saved, we search WhatsApp instead
        if not any(char.isdigit() for char in clean_phone):
            launch_browser_async("https://web.whatsapp.com")
            return {
                "success": True,
                "message": f"WhatsApp Web khol diya hai taake aap {phone} ko search karke message paste kar sakein."
            }

        if not clean_phone.startswith("+"):
            if clean_phone.startswith("0"):
                clean_phone = "+92" + clean_phone[1:]
            else:
                clean_phone = "+92" + clean_phone

        encoded_message = urllib.parse.quote(message)
        url = f"https://web.whatsapp.com/send?phone={clean_phone}&text={encoded_message}"
        
        # ⚡ Safe Async Desktop Pop-up
        launch_browser_async(url)
        return {
            "success": True, 
            "message": f"WhatsApp Web par {phone} ka chat khol diya hai. Bas send click kar dein!"
        }
    except Exception as e:
        return {"success": False, "message": f"WhatsApp error: {e}"}


def send_instagram_message(username: str, message: str) -> dict:
    """⚡ Standardized Background Safe Instagram Redirect Launcher"""
    try:
        clean_user = str(username).replace("@", "").strip()
        
        # Open user direct profile safely
        url = f"https://www.instagram.com/{clean_user}/"
        launch_browser_async(url)
        
        try:
            import pyperclip
            pyperclip.copy(message)
            note = "Message copy ho chuka hai, profile open hote hi DM mein paste (Ctrl+V) kar dein!"
        except Exception:
            note = f"Message: '{message}'"

        return {
            "success": True, 
            "message": f"Instagram par {username} ki profile open kar di hai. {note}"
        }
    except Exception as e:
        return {"success": False, "message": f"Instagram error: {e}"}


def confirm_and_send(draft: dict) -> dict:
    platform = draft.get("platform")
    contact_id = draft.get("contact_id")
    message = draft.get("message")
    
    if platform == "whatsapp":
        return send_whatsapp_message(contact_id, message)
    elif platform == "instagram":
        return send_instagram_message(contact_id, message)
    return {"success": False, "message": "Invalid platform."}


def cancel_message(draft: dict) -> dict:
    return {"success": True, "message": "Message cancel kar diya gaya."}


def edit_message(draft: dict, new_message: str) -> dict:
    draft["message"] = new_message.strip()
    return {
        "success": True,
        "message": "Draft message update kar diya.",
        "draft": draft
    }
"""
LUCIA Gmail Reader & Sender V3 (With State-Cache for Voice & UI)
- Unified state caching for zero-latency confirmation flow
- SSL/Network retry with exponential backoff
- Read, Search, Summarize, Send, Draft, Reply
- Duplicate send protection
"""
import os
import uuid
import base64
import logging
import time
import re
import ssl
from pathlib import Path
from email.utils import parsedate_to_datetime, formatdate, make_msgid
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from typing import Optional, Callable, Any

logger = logging.getLogger("lucia.tools.gmail")
logger.setLevel(logging.INFO)
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter(
        "[%(asctime)s] %(levelname)s | %(message)s", datefmt="%H:%M:%S"
    ))
    logger.addHandler(handler)

# Paths
PROJECT_ROOT = Path(__file__).resolve().parent.parent
CREDENTIALS_FILE = PROJECT_ROOT / "credentials.json"
TOKEN_FILE = PROJECT_ROOT / "token.json"

REQUIRED_SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]

MAX_RETRIES = 3
BACKOFF_BASE = 1.0

# 🧠 Global State Cache for Voice & Text Confirmation
_last_prepared_draft: Optional[dict] = None
_send_log: list[dict] = []
MAX_SEND_LOG = 50


# ==========================================
# RETRY & ERROR CLASSIFICATION
# ==========================================
class GmailAuthError(Exception): pass
class GmailScopeError(Exception): pass
class GmailPermanentError(Exception): pass
class GmailTransientError(Exception): pass


def _classify_error(error: Exception) -> Exception:
    err_str = str(error).lower()
    err_type = type(error).__name__

    if isinstance(error, (ssl.SSLError, ConnectionResetError, BrokenPipeError,
                          ConnectionAbortedError, TimeoutError, OSError)):
        return GmailTransientError(f"Network error: {error}")
    if "unexpected_eof" in err_str or "eof occurred" in err_str:
        return GmailTransientError(f"SSL connection dropped: {error}")
    if "connection reset" in err_str or "broken pipe" in err_str:
        return GmailTransientError(f"Connection lost: {error}")
    if "timed out" in err_str or "timeout" in err_str:
        return GmailTransientError(f"Request timeout: {error}")

    if "HttpError" in err_type or "http" in err_str:
        if "401" in err_str or "unauthorized" in err_str:
            return GmailAuthError("Authentication expired or invalid.")
        if "403" in err_str:
            if "insufficient" in err_str or "scope" in err_str or "permission" in err_str:
                return GmailScopeError("Gmail permission/scope insufficient.")
            return GmailPermanentError(f"Access denied: {error}")
        if "429" in err_str or "rate limit" in err_str:
            return GmailTransientError("Gmail rate limit hit.")
        if "500" in err_str or "502" in err_str or "503" in err_str or "504" in err_str:
            return GmailTransientError(f"Gmail server error: {error}")
        if "400" in err_str or "404" in err_str:
            return GmailPermanentError(f"Invalid request: {error}")

    return GmailTransientError(f"Unknown error: {error}")


def _execute_with_retry(api_call: Callable, operation: str = "Gmail API") -> Any:
    last_error = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            result = api_call()
            if attempt > 1:
                logger.info(f"{operation} succeeded on attempt {attempt}/{MAX_RETRIES}")
            return result
        except Exception as raw_error:
            classified = _classify_error(raw_error)
            last_error = classified

            if isinstance(classified, (GmailAuthError, GmailScopeError, GmailPermanentError)):
                logger.error(f"{operation} permanent failure: {classified}")
                raise classified

            if attempt < MAX_RETRIES:
                delay = BACKOFF_BASE * (2 ** (attempt - 1))
                logger.warning(f"{operation} failed (attempt {attempt}/{MAX_RETRIES}): {classified}. Retrying in {delay:.0f}s...")
                time.sleep(delay)
            else:
                logger.error(f"{operation} failed after {MAX_RETRIES} attempts: {classified}")

    raise GmailTransientError(f"{operation} failed after {MAX_RETRIES} attempts. Last error: {last_error}")


# ==========================================
# AUTHENTICATION
# ==========================================
def _get_gmail_service():
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build
    import httplib2
    from google_auth_httplib2 import AuthorizedHttp

    creds = None
    if TOKEN_FILE.exists():
        try:
            creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), REQUIRED_SCOPES)
        except Exception as e:
            logger.warning(f"Token load failed: {e}")
            creds = None

    needs_reauth = False
    if creds and creds.valid:
        token_scopes = set(creds.scopes or [])
        required_set = set(REQUIRED_SCOPES)
        if not required_set.issubset(token_scopes):
            logger.warning(f"Token scopes insufficient. Re-authentication required.")
            needs_reauth = True

    if not creds or not creds.valid or needs_reauth:
        if creds and creds.expired and creds.refresh_token and not needs_reauth:
            try:
                creds.refresh(Request())
            except Exception as e:
                logger.warning(f"Token refresh failed: {e}. Re-authenticating...")
                creds = None

        if not creds or needs_reauth:
            if not CREDENTIALS_FILE.exists():
                return None, "credentials.json nahi mila! Project root mein rakhein."
            try:
                flow = InstalledAppFlow.from_client_secrets_file(str(CREDENTIALS_FILE), REQUIRED_SCOPES)
                creds = flow.run_local_server(port=0)
            except Exception as e:
                return None, f"Gmail authentication fail: {e}"

        try:
            with open(TOKEN_FILE, "w") as f:
                f.write(creds.to_json())
            os.chmod(str(TOKEN_FILE), 0o600)
        except Exception as e:
            logger.warning(f"Token save warning: {e}")

    try:
        http = httplib2.Http(timeout=30)
        authorized_http = AuthorizedHttp(creds, http=http)
        service = build("gmail", "v1", http=authorized_http)
        return service, None
    except Exception as e:
        return None, f"Gmail service build fail: {e}"


def _user_friendly_error(error: Exception) -> str:
    if isinstance(error, GmailAuthError):
        return "Google authentication zaroori hai. 'gmail_setup.py' dobara run karein."
    if isinstance(error, GmailScopeError):
        return "LUCIA ke paas is Gmail action ki permission nahi hai. 'gmail_setup.py' dobara run karein."
    if isinstance(error, GmailTransientError):
        return "Gmail connection temporarily fail ho raha hai. 3 attempts ke baad request fail hui."
    if isinstance(error, GmailPermanentError):
        return f"Gmail request fail hui: {error}"
    return f"Gmail error: {error}"


# ==========================================
# EMAIL PARSING HELPERS
# ==========================================
def _decode_body(payload: dict) -> str:
    body_text = ""
    if "body" in payload and payload["body"].get("data"):
        raw = payload["body"]["data"]
        body_text = base64.urlsafe_b64decode(raw).decode("utf-8", errors="ignore")

    if not body_text and "parts" in payload:
        for part in payload["parts"]:
            mime = part.get("mimeType", "")
            if mime == "text/plain" and part.get("body", {}).get("data"):
                raw = part["body"]["data"]
                body_text = base64.urlsafe_b64decode(raw).decode("utf-8", errors="ignore")
                break
            elif mime == "text/html" and part.get("body", {}).get("data"):
                raw = part["body"]["data"]
                html = base64.urlsafe_b64decode(raw).decode("utf-8", errors="ignore")
                body_text = _strip_html(html)
                break

    body_text = re.sub(r'\s+', ' ', body_text).strip()
    if len(body_text) > 1500:
        body_text = body_text[:1500] + " ... [truncated]"
    return body_text


def _strip_html(html: str) -> str:
    try:
        from bs4 import BeautifulSoup
        return BeautifulSoup(html, "html.parser").get_text(separator=" ", strip=True)
    except ImportError:
        return re.sub(r'<[^>]+>', ' ', html)


def _get_header(headers: list, name: str) -> str:
    for h in headers:
        if h["name"].lower() == name.lower():
            return h["value"]
    return ""


def _parse_timestamp(date_str: str) -> str:
    try:
        dt = parsedate_to_datetime(date_str)
        return dt.strftime("%d %b %Y, %I:%M %p")
    except Exception:
        return date_str


# ==========================================
# 📧 READ TOOLS
# ==========================================
def authenticate_gmail() -> dict:
    service, error = _get_gmail_service()
    if error:
        return {"success": False, "message": error}
    try:
        profile = _execute_with_retry(lambda: service.users().getProfile(userId="me").execute(), "get_profile")
        email = profile.get("emailAddress", "unknown")
        return {"success": True, "message": f"Gmail connected: {email}", "email": email}
    except Exception as e:
        return {"success": False, "message": _user_friendly_error(e)}


def fetch_unread_emails(max_results: int = 10) -> dict:
    service, error = _get_gmail_service()
    if error:
        return {"success": False, "message": error}
    try:
        results = _execute_with_retry(lambda: service.users().messages().list(userId="me", q="is:unread in:inbox", maxResults=max_results).execute(), "list_unread")
        messages = results.get("messages", [])
        if not messages:
            return {"success": True, "message": "Koi unread email nahi hai!", "emails": [], "count": 0}

        emails = []
        for msg_meta in messages:
            msg = _execute_with_retry(lambda mid=msg_meta["id"]: service.users().messages().get(userId="me", id=mid, format="full").execute(), f"get_message_{msg_meta['id'][:8]}")
            headers = msg.get("payload", {}).get("headers", [])
            emails.append({
                "id": msg_meta["id"],
                "from": _get_header(headers, "From"),
                "subject": _get_header(headers, "Subject") or "(No Subject)",
                "date": _parse_timestamp(_get_header(headers, "Date")),
                "body_preview": _decode_body(msg.get("payload", {}))[:500],
                "snippet": msg.get("snippet", "")
            })
        return {"success": True, "message": f"{len(emails)} unread emails mile.", "emails": emails, "count": len(emails)}
    except Exception as e:
        return {"success": False, "message": _user_friendly_error(e)}


def read_email(email_id: str) -> dict:
    service, error = _get_gmail_service()
    if error:
        return {"success": False, "message": error}
    try:
        msg = _execute_with_retry(lambda: service.users().messages().get(userId="me", id=email_id, format="full").execute(), "read_email")
        headers = msg.get("payload", {}).get("headers", [])
        return {
            "success": True, "message": "Email padh liya.",
            "email": {
                "from": _get_header(headers, "From"),
                "to": _get_header(headers, "To"),
                "subject": _get_header(headers, "Subject"),
                "date": _parse_timestamp(_get_header(headers, "Date")),
                "body": _decode_body(msg.get("payload", {}))
            }
        }
    except Exception as e:
        return {"success": False, "message": _user_friendly_error(e)}


def search_emails(query: str, max_results: int = 5) -> dict:
    service, error = _get_gmail_service()
    if error:
        return {"success": False, "message": error}
    try:
        results = _execute_with_retry(lambda: service.users().messages().list(userId="me", q=query, maxResults=max_results).execute(), "search_emails")
        messages = results.get("messages", [])
        if not messages:
            return {"success": True, "message": f"'{query}' ke liye koi email nahi mila.", "emails": []}

        emails = []
        for msg_meta in messages:
            msg = _execute_with_retry(lambda mid=msg_meta["id"]: service.users().messages().get(userId="me", id=mid, format="metadata").execute(), "search_get")
            headers = msg.get("payload", {}).get("headers", [])
            emails.append({
                "from": _get_header(headers, "From"),
                "subject": _get_header(headers, "Subject"),
                "date": _parse_timestamp(_get_header(headers, "Date")),
                "snippet": msg.get("snippet", "")
            })
        return {"success": True, "message": f"{len(emails)} emails mile.", "emails": emails}
    except Exception as e:
        return {"success": False, "message": _user_friendly_error(e)}


def summarize_emails(max_results: int = 10) -> dict:
    fetch_result = fetch_unread_emails(max_results)
    if not fetch_result["success"]:
        return fetch_result

    emails = fetch_result.get("emails", [])
    if not emails:
        return {"success": True, "message": "Inbox clean hai bhai! Koi unread email nahi hai.", "emails": [], "summary": "No unread emails.", "urgent": []}

    email_text = ""
    for i, em in enumerate(emails, 1):
        email_text += f"\n--- Email {i} ---\nFrom: {em['from']}\nSubject: {em['subject']}\nDate: {em['date']}\nPreview: {em['body_preview']}\n"

    try:
        from llm_gateway import gateway
        from langchain_core.messages import HumanMessage

        analysis_prompt = f"""Analyze these {len(emails)} unread emails and summarize them in Roman Urdu, noting urgent threads:
{email_text}
"""
        response = gateway.invoke([HumanMessage(content=analysis_prompt)], task_type="summary")
        ai_summary = response.content.strip()
    except Exception as e:
        ai_summary = f"AI summary generate nahi ho saki: {e}"

    return {
        "success": True,
        "message": f"{len(emails)} unread emails analyze ho gaye.",
        "emails": emails, "summary": ai_summary,
        "urgent": [], "urgent_count": 0, "count": len(emails)
    }


# ==========================================
# 📤 SEND & CONFIRMATION CORE (With Cache)
# ==========================================
def prepare_email(to: str, subject: str, body: str, cc: str = "") -> dict:
    """
    Prepare email and cache it.
    Matches the exact keys required by Streamlit's Draft Card UI!
    """
    global _last_prepared_draft
    logger.info(f"prepare_email: to={to}, subject={subject}")

    if not to or "@" not in to:
        return {"success": False, "message": "Valid email address zaroori hai."}
    if not subject.strip():
        return {"success": False, "message": "Subject khali nahi ho sakta."}
    if not body.strip():
        return {"success": False, "message": "Email body khali nahi ho sakti."}

    draft_id = str(uuid.uuid4())[:8]
    
    # ⚡ Cache with precise unified keys so Streamlit renders it instantly
    _last_prepared_draft = {
        "id": draft_id,
        "platform": "gmail",
        "to": to.strip(),
        "subject": subject.strip(),
        "body": body.strip(),
        "cc": cc.strip() if cc else "",
        # Dynamic keys matching UI component
        "contact_name": to.strip(),
        "contact_id": to.strip(),
        "message": body.strip()
    }

    preview = f"""Ye email send kar doon?
    
To: `{to}`
Subject: `{subject}`
{f"CC: `{cc}`" if cc else ""}

--- Body ---
{body}
"""
    return {
        "success": True,
        "message": preview,
        "draft": _last_prepared_draft
    }


def send_email(to: str, subject: str, body: str, cc: str = "", confirm: bool = False) -> dict:
    """Sends the email with active unique message ID to prevent duplicate sending"""
    logger.info(f"send_email: to={to}, subject={subject}, confirm={confirm}")

    if not confirm:
        return {"success": False, "message": "Email bhejne ke liye confirm=True zaroori hai."}

    service, error = _get_gmail_service()
    if error:
        return {"success": False, "message": error}

    unique_send_id = str(uuid.uuid4())[:12]
    msg_id_header = make_msgid(domain="lucia.local")

    try:
        if cc:
            message = MIMEMultipart()
            message.attach(MIMEText(body, "plain", "utf-8"))
        else:
            message = MIMEText(body, "plain", "utf-8")

        message["To"] = to.strip()
        message["Subject"] = subject.strip()
        message["Date"] = formatdate(localtime=True)
        message["Message-ID"] = msg_id_header
        message["X-LUCIA-Send-ID"] = unique_send_id
        if cc:
            message["Cc"] = cc.strip()

        raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")

        sent = _execute_with_retry(
            lambda: service.users().messages().send(userId="me", body={"raw": raw_message}).execute(),
            operation="send_email"
        )

        sent_id = sent.get("id", "unknown")
        _send_log.append({
            "id": sent_id, "lucia_id": unique_send_id,
            "to": to, "subject": subject, "timestamp": datetime.now().isoformat()
        })
        if len(_send_log) > MAX_SEND_LOG:
            _send_log.pop(0)

        return {
            "success": True,
            "message": "Email successfully send ho gayi bhai. ✅",
            "to": to,
            "subject": subject,
            "email_id": sent_id
        }
    except Exception as e:
        logger.error(f"send_email FAIL: {e}")
        return {"success": False, "message": _user_friendly_error(e)}


def confirm_last_email() -> dict:
    """Triggered on voice 'bhej do' or 'send it' — sends cached draft"""
    global _last_prepared_draft
    if not _last_prepared_draft:
        return {"success": False, "message": "Koi active email draft nahi mila. Pehle email taiyaar karne ko bolein."}
    
    result = send_email(
        to=_last_prepared_draft["to"],
        subject=_last_prepared_draft["subject"],
        body=_last_prepared_draft["body"],
        cc=_last_prepared_draft.get("cc", ""),
        confirm=True
    )
    if result["success"]:
        _last_prepared_draft = None  # Clear cache
    return result


def cancel_last_email() -> dict:
    """Triggered on voice 'cancel' — clears cache"""
    global _last_prepared_draft
    if not _last_prepared_draft:
        return {"success": False, "message": "Cancel karne ke liye koi active email draft nahi hai."}
    _last_prepared_draft = None
    return {"success": True, "message": "Email draft cancel kar diya gaya. ✅"}


# Legacy aliases
def create_draft(to: str, subject: str, body: str, cc: str = "") -> dict:
    service, error = _get_gmail_service()
    if error: return {"success": False, "message": error}
    try:
        message = MIMEText(body, "plain", "utf-8")
        message["To"] = to.strip()
        message["Subject"] = subject.strip()
        raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")
        draft = _execute_with_retry(lambda: service.users().drafts().create(userId="me", body={"message": {"raw": raw_message}}).execute(), "create_draft")
        return {"success": True, "message": f"Draft bana diya hai! Gmail ID: {draft.get('id')}"}
    except Exception as e:
        return {"success": False, "message": _user_friendly_error(e)}


def reply_email(email_id: str, body: str) -> dict:
    service, error = _get_gmail_service()
    if error: return {"success": False, "message": error}
    try:
        original = _execute_with_retry(lambda: service.users().messages().get(userId="me", id=email_id, format="full").execute(), "get_original_for_reply")
        headers = original.get("payload", {}).get("headers", [])
        original_from = _get_header(headers, "From")
        original_subject = _get_header(headers, "Subject")
        reply_subject = f"Re: {original_subject}" if not original_subject.lower().startswith("re:") else original_subject
        
        message = MIMEText(body, "plain", "utf-8")
        message["To"] = original_from
        message["Subject"] = reply_subject
        raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")
        sent = _execute_with_retry(lambda: service.users().messages().send(userId="me", body={"raw": raw_message, "threadId": original.get("threadId")}).execute(), "reply_email")
        return {"success": True, "message": f"Reply bhej diya! ID: {sent.get('id')}"}
    except Exception as e:
        return {"success": False, "message": _user_friendly_error(e)}

def _get_user_email_profile() -> dict:
    """
    Pull user's personal details from memories.
    Cleanly parses descriptive sentences (e.g., 'Mahadi is a BBit student at Air University')
    into professional designations, preventing raw database sentences from rendering in signature.
    """
    profile = {
        "name": "",
        "email": "",
        "signature": "",
        "role": "",
        "organization": ""
    }
    
    try:
        from database import get_global_memories
        mems = get_global_memories()
        
        for m in mems:
            mem_text = m.get("memory", "").strip()
            mem_lower = mem_text.lower()
            
            # 1. Extract Name
            if "name" in mem_lower and "is" in mem_lower:
                parts = mem_text.split("is")
                if len(parts) > 1:
                    profile["name"] = parts[-1].strip().rstrip(".")
            
            # 2. Extract Email
            if "email" in mem_lower and "@" in mem_text:
                import re
                emails = re.findall(r'[\w.+-]+@[\w-]+\.[\w.]+', mem_text)
                if emails:
                    profile["email"] = emails[0]
            
            # 3. 🧠 Smart Regex Parser for Designation & Organization
            # Matches: "[Name] is a/an [Role] at [Organization]"
            import re
            pattern = r"(?i)^(?:user|he|she|[a-zA-Z]+)\s+(?:is\s+a|is\s+an|works\s+as|studies|is\s+a\s+student\s+at)\s+(.+?)\s+at\s+(.+)$"
            match = re.match(pattern, mem_text.rstrip("."))
            
            if match:
                profile["role"] = match.group(1).strip().title()
                profile["organization"] = match.group(2).strip().title()
            else:
                # Fallback parser if "at" is missing but role keywords exist
                if any(w in mem_lower for w in ["student", "developer", "engineer", "designer", "manager"]):
                    role_match = re.search(r"(?i)(?:is\s+a|is\s+an|works\s+as)\s+([^,.]+)", mem_text)
                    if role_match:
                        profile["role"] = role_match.group(1).strip().title()
                        
                if any(w in mem_lower for w in ["university", "company", "corporation", "inc", "ltd"]):
                    org_match = re.search(r"(?i)(?:at|in|for)\s+([^,.]+)", mem_text)
                    if org_match:
                        profile["organization"] = org_match.group(1).strip().title()

        # 4. Construct clean, professional signature
        sig_parts = []
        if profile["name"]:
            sig_parts.append(profile["name"])
        
        # Combine parsed Role and Org: "Role at Org"
        role_org_line = ""
        if profile["role"] and profile["organization"]:
            role_org_line = f"{profile['role']} at {profile['organization']}"
        elif profile["role"]:
            role_org_line = profile["role"]
        elif profile["organization"]:
            role_org_line = profile["organization"]
            
        if role_org_line:
            sig_parts.append(role_org_line)
            
        if profile["email"]:
            sig_parts.append(profile["email"])
            
        profile["signature"] = "\n".join(sig_parts)
        
    except Exception as e:
        logger.warning(f"Could not load user profile: {e}")
    
    return profile


def prepare_email(to: str = "", subject: str = "", body: str = "", 
                  cc: str = "", auto_sign: bool = True) -> dict:
    """
    Prepare email with auto-filled user details from global memory.
    Ensures signature is only appended if it is not already written in the body.
    """
    global _last_prepared_draft
    logger.info(f"prepare_email: to={to}, subject={subject}")

    # 1. Load user profile for auto-fill
    user_profile = _get_user_email_profile()
    
    # 2. Check for missing required fields
    missing = []
    if not to or "@" not in to:
        missing.append("recipient (email address)")
    if not subject.strip():
        missing.append("subject")
    if not body.strip():
        missing.append("body")
    
    if missing:
        questions = "\n".join([f"  • {m}" for m in missing])
        return {
            "success": False,
            "needs_clarification": True,
            "message": f"Bhai, email taiyaar karne ke liye mujhe yeh details chahiye:\n{questions}\n\nBata do, main ekdum professional draft ready kar deti hoon!",
            "missing_fields": missing
        }

    # 3. Clean up the body generator placeholders
    final_body = body.replace("[Use User Name from memories]", user_profile.get("name", "Mahadi")).strip()
    
    # 4. Auto-sign: Only append if name/signature is NOT already written at the end
    if auto_sign and user_profile.get("signature"):
        # Check if user's name is already at the end of the text
        body_last_lines = final_body.lower().split("\n")[-4:]
        name_already_present = any(user_profile["name"].lower() in line for line in body_last_lines if line)
        
        if not name_already_present:
            final_body += f"\n\nRegards,\n{user_profile['signature']}"

    draft_id = str(uuid.uuid4())[:8]
    
    _last_prepared_draft = {
        "id": draft_id,
        "platform": "gmail",
        "to": to.strip(),
        "subject": subject.strip(),
        "body": final_body,
        "cc": cc.strip() if cc else "",
        "contact_name": to.strip(),
        "contact_id": to.strip(),
        "message": final_body
    }

    preview = f"""Ye email send kar doon?

**To:** `{to}`
**Subject:** `{subject}`
{f"**CC:** `{cc}`" if cc else ""}

--- Body ---
{final_body}
--- End ---"""

    return {
        "success": True,
        "message": preview,
        "draft": _last_prepared_draft,
        "auto_filled": {
            "name": user_profile.get("name", ""),
            "signature_added": auto_sign and not name_already_present and bool(user_profile.get("signature"))
        }
    }
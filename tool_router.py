"""
Tool Router: LUCIA ka decision brain
Optimized with Global Profile memories to auto-fill personalized professional email drafts.
"""
import json
import re
from langchain_core.messages import HumanMessage
from tools import (
    open_website, open_google, open_youtube,
    search_youtube, play_youtube,
    web_search,
    list_directory, read_file, write_file, create_file,
    edit_file, delete_file, create_directory, open_file,
    generate_code_file,
    draft_message,
    search_instagram, search_whatsapp,
    execute_command,
    authenticate_gmail, fetch_unread_emails,
    summarize_emails, read_email, search_emails,
    prepare_email, send_email, create_draft, reply_email,
    confirm_last_email, cancel_last_email,
)

# Available tools schema
TOOLS_SCHEMA = """
Available tools you can use:

1. open_website(url) - Opens ANY website (github, netflix, chatgpt, etc.)
2. open_google(query) - Opens Google homepage or search
3. open_youtube() - Opens YouTube homepage
4. search_youtube(query) - Opens YouTube search results list
5. play_youtube(query) - DIRECTLY PLAYS top video/song on YouTube
6. web_search(query) - Search web for live information
7. list_directory(path) - List files in folder
8. read_file(path) - Read file contents
9. write_file(path, content) - Create/write a file
10. create_directory(path) - Create folder
11. execute_command(command, cwd) - Run local shell command safely

GMAIL:
12. authenticate_gmail() - Connect/test Gmail
13. fetch_unread_emails(max_results) - Get unread emails
14. summarize_emails(max_results) - AI summary + urgent detection
15. read_email(email_id) - Read specific email
16. search_emails(query, max_results) - Search emails
17. prepare_email(to, subject, body, cc) - Prepare email and generate a draft review card (DOES NOT SEND)
18. confirm_last_email() - Send the last prepared email (Call when user says "haan bhej do", "send it", "bhej do")
19. cancel_last_email() - Cancel/discard the last prepared email (Call when user says "cancel", "cancel karo", "mat bhejo")
20. draft_message(platform, contact, message) - Prepare WhatsApp/Instagram message draft
"""

TOOL_MAP = {
    "open_website": open_website,
    "open_google": open_google,
    "open_youtube": open_youtube,
    "search_youtube": search_youtube,
    "play_youtube": play_youtube,
    "web_search": web_search,
    "list_directory": list_directory,
    "read_file": read_file,
    "write_file": write_file,
    "create_file": create_file,
    "edit_file": edit_file,
    "delete_file": delete_file,
    "create_directory": create_directory,
    "execute_command": execute_command,
    "generate_code_file": generate_code_file,
    "draft_message": draft_message,
    "search_instagram": search_instagram,
    "search_whatsapp": search_whatsapp,
    "authenticate_gmail": authenticate_gmail,
    "fetch_unread_emails": fetch_unread_emails,
    "summarize_emails": summarize_emails,
    "read_email": read_email,
    "search_emails": search_emails,
    "prepare_email": prepare_email,
    "send_email": send_email,
    "create_draft": create_draft,
    "reply_email": reply_email,
    "confirm_last_email": confirm_last_email,
    "cancel_last_email": cancel_last_email,
}


def decide_action(user_msg: str, llm) -> dict:
    """
    Ask LLM: Is this a tool call or normal chat?
    Injects global user memories to write customized professional emails.
    """
    msg_clean = user_msg.lower().strip()
    
    # ⚡ Fast Path: Map direct voice confirmation keys instantly
    if msg_clean in ["haan bhej do", "send kar do", "bhej do", "bhej de", "send it", "yes send it"]:
        return {"action": "tool", "tool": "confirm_last_email", "params": {}}
    if msg_clean in ["cancel karo", "cancel", "mat bhejo", "discard", "discard it"]:
        return {"action": "tool", "tool": "cancel_last_email", "params": {}}

    # 🧠 Load Global Memories to make the Router intelligent about the User
    from database import get_global_memories
    mems = get_global_memories()
    memories_text = "No profile memories found."
    if mems:
        memories_text = "\n".join([f"- {m['memory']}" for m in mems])

    router_prompt = f"""You are LUCIA's action router. Analyze the user's message and decide:

- If user wants conversation ONLY, return: {{"action": "chat"}}
- If user wants to PERFORM an action, return the appropriate tool call.

{TOOLS_SCHEMA}

=== USER PROFILE MEMORIES ===
Use these real details about the user to write highly tailored, professional email bodies. 
Do NOT write generic placeholders like '[My Name]' or '[My University]' in the email body. Replace them with the actual facts below:
{memories_text}

EMAIL WRITING & CLARIFICATION RULES:
- When user asks to write/send a professional email (e.g., job application, leave, project update): Use the USER PROFILE MEMORIES to draft a complete, customized, professional email body.
- If recipient email is not provided, set "to": "" so the tool triggers clarification questions.
- If user says "bhej do" / "send it" -> use confirm_last_email.
- Only respond in valid JSON, nothing else.

Examples:

User: "hr@techcorp.com ko cloud engineer internship ke liye professional email likho"
{{"action": "tool", "tool": "prepare_email", "params": {{"to": "hr@techcorp.com", "subject": "Application for Cloud Engineer Internship", "body": "Dear Hiring Manager,\\n\\nI hope this email finds you well.\\n\\nI am writing to express my strong interest in the Cloud Engineer Internship position at TechCorp. Currently, I am pursuing my BBIT at Air University, which has equipped me with a strong foundation in managing IT systems and data architectures.\\n\\nAs a Python developer with a deep passion for cloud systems and automation, I am eager to apply my skills to real-world projects at TechCorp. Thank you for your time and consideration.\\n\\nRegards,\\n[Use User Name from memories]"}}}}

User message: "{user_msg}"

Respond with valid JSON only:"""

    try:
        response = llm.invoke([HumanMessage(content=router_prompt)])
        text = response.content.strip()
        
        if "```" in text:
            text = re.sub(r'```(?:json)?', '', text).strip()
        
        match = re.search(r'\{.*\}', text, re.DOTALL)
        if match:
            text = match.group(0)
        
        decision = json.loads(text)
        return decision
    except Exception as e:
        print(f"[Router Error]: {e}")
        return {"action": "chat"}


def execute_tool(decision: dict) -> dict:
    tool_name = decision.get("tool")
    params = decision.get("params", {})
    
    if tool_name not in TOOL_MAP:
        return {"success": False, "message": f"Tool '{tool_name}' mojood nahi."}
    
    try:
        tool_fn = TOOL_MAP[tool_name]
        result = tool_fn(**params)
        return result
    except Exception as e:
        return {"success": False, "message": f"Tool execute nahi hua: {e}"}
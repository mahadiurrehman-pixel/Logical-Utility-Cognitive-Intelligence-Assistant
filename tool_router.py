"""
Tool Router: LUCIA ka decision brain
Optimized with local heuristic pre-routing to prevent unnecessary LLM calls.
"""
import json
import re
from langchain_core.messages import HumanMessage
from tools import (
    open_website, open_google, open_youtube,
    search_youtube, play_youtube,
    web_search,
    list_files, read_file, write_file, create_folder, open_file, delete_file_safe,
    generate_code_file,
    draft_message,
    search_instagram, search_whatsapp
)

# Available tools schema
TOOLS_SCHEMA = """
Available tools you can use:

1. open_website(url) - Opens ANY website (github, netflix, chatgpt, etc.)
2. open_google(query) - Opens Google homepage or search
3. open_youtube() - Opens YouTube homepage
4. search_youtube(query) - Opens YouTube search results list
5. play_youtube(query) - DIRECTLY PLAYS top video/song on YouTube
6. web_search(query) - Search web for live information, definitions, facts, weather, or real-time questions
7. list_files(folder) - List files in folder
8. read_file(path) - Read file contents
9. write_file(path, content) - Create/write a file
10. create_folder(path) - Create folder
11. open_file(path) - Open local file in default OS app
12. generate_code_file(path, code, language) - Save generated code to file
13. draft_message(platform, contact, message) - Prepare WhatsApp/Instagram draft
14. search_instagram(query) - Search on Instagram
15. search_whatsapp(query) - Search WhatsApp for a contact/chat
"""

TOOL_MAP = {
    "open_website": open_website,
    "open_google": open_google,
    "open_youtube": open_youtube,
    "search_youtube": search_youtube,
    "play_youtube": play_youtube,
    "web_search": web_search,
    "list_files": list_files,
    "read_file": read_file,
    "write_file": write_file,
    "create_folder": create_folder,
    "open_file": open_file,
    "generate_code_file": generate_code_file,
    "draft_message": draft_message,
    "search_instagram": search_instagram,
    "search_whatsapp": search_whatsapp,
}


def message_might_need_tool(user_msg: str) -> bool:
    """
    Highly-optimized Heuristic fast-path check.
    Returns True if user's input matches potential action triggers.
    Filters out basic greetings, direct queries without action intent, and casual talk locally.
    """
    msg = user_msg.lower().strip()
    
    # Tool action keywords
    action_keywords = [
        "kholo", "open", "go to", "website", ".com", ".org", ".net", ".ai", "visit", # Browser
        "search", "google", "dhoondo", "fetch", "find", "pata karo", "what is", "who is", "latest", "news", "weather", "gold rate", # Search / RAG
        "youtube", "play", "chalao", "lagao", "sunao", "video", # YouTube
        "folder", "directory", "file", "create", "write", "banao", "likho", "read", "padho", "delete", "remove", "khatam", # File / Code Operations
        "message", "whatsapp", "instagram", "dm", "bhejo", "draft" # Messaging
    ]
    return any(word in msg for word in action_keywords)


def decide_action(user_msg: str, llm) -> dict:
    """
    Ask LLM: Is this a tool call or normal chat?
    Returns: {"action": "chat" or "tool", "tool": "...", "params": {...}}
    """
    # ⚡ Rate limit optimization: Skip LLM call if local heuristics find no tool keywords
    if not message_might_need_tool(user_msg):
        return {"action": "chat"}

    router_prompt = f"""You are LUCIA's action router. Analyze the user's message and decide:

- If user wants conversation/coding advice ONLY, return: {{"action": "chat"}}
- If user wants to PERFORM an action, return the appropriate tool call.

{TOOLS_SCHEMA}

RULES:
- For factual, live queries, definitions ("What is Python", "Who is Babar Azam", "Google se fetch karo..."): use `web_search`.
- When user says "search on Instagram" or "Instagram par dhoondo/search karo" or gives a profile/hashtag on IG -> use `search_instagram`
- When user says "search on WhatsApp" or "WhatsApp par [person] ko dhoondo/search karo" -> use `search_whatsapp`
- When user says "message bhejo/likho/draft karo" -> use `draft_message`
- When user says "play" / "chalao" on YouTube -> use `play_youtube`
- Return valid JSON ONLY.

Examples:
User: "Instagram par AI Art search karo"
{{"action": "tool", "tool": "search_instagram", "params": {{"query": "AI Art"}}}}

User: "WhatsApp par Ali ko search karo"
{{"action": "tool", "tool": "search_whatsapp", "params": {{"query": "Ali"}}}}

User: "Ali ko WhatsApp pe message likho ke kal meeting hai"
{{"action": "tool", "tool": "draft_message", "params": {{"platform": "whatsapp", "contact": "Ali", "message": "Kal meeting hai."}}}}

User: "YouTube par LoFi music chalao"
{{"action": "tool", "tool": "play_youtube", "params": {{"query": "LoFi music"}}}}

User message: "{user_msg}"

Respond with valid JSON only:"""

    try:
        # LLM Invocation wrapped directly with exception handling in lucia.py
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
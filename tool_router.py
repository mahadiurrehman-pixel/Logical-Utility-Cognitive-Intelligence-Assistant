"""
Tool Router: LUCIA ka decision brain
Strict rules for file creation, fixing, updating, and execution on disk.
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

TOOLS_SCHEMA = """
Available tools:

BROWSER:
1. open_website(url) - Opens ANY website (github, netflix, chatgpt, etc)
2. open_google(query) - Opens Google or search
3. open_youtube() - Opens YouTube homepage
4. search_youtube(query) - Search YouTube results
5. play_youtube(query) - DIRECTLY play top video
6. web_search(query) - Live web info search

FILESYSTEM (USE THESE to create, update, or fix files on disk):
7. list_directory(path) - List folder contents
8. read_file(path) - Read file contents
9. write_file(path, content) - Create or OVERWRITE/UPDATE a file on disk with full code/content
10. create_file(path, content) - Create NEW file
11. edit_file(path, old_text, new_text) - Find & replace in file
12. delete_file(path, confirm) - Delete file (confirm=True REQUIRED)
13. create_directory(path) - Create folder

TERMINAL:
14. execute_command(command, cwd) - Run terminal command (python3, bash, ls, etc)

MESSAGING & GMAIL:
15. draft_message(platform, contact, message) - WhatsApp/Instagram draft
16. search_instagram(query) - IG search
17. search_whatsapp(query) - WhatsApp search
18. prepare_email(to, subject, body, cc) - Prepare email draft
19. confirm_last_email() - Send last prepared email
20. cancel_last_email() - Cancel last prepared email
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
    "list_files": list_directory,
    "create_folder": create_directory,
    "open_file": read_file,
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
    msg_clean = user_msg.lower().strip()
    
    if msg_clean in ["haan bhej do", "send kar do", "bhej do", "bhej de", "send it", "yes send it"]:
        return {"action": "tool", "tool": "confirm_last_email", "params": {}}
    if msg_clean in ["cancel karo", "cancel", "mat bhejo", "discard", "discard it"]:
        return {"action": "tool", "tool": "cancel_last_email", "params": {}}

    # Load Global Memories
    from database import get_global_memories
    mems = get_global_memories()
    memories_text = "No profile memories found."
    if mems:
        memories_text = "\n".join([f"- {m['memory']}" for m in mems])

    router_prompt = f"""You are LUCIA's action router. Analyze the user's message and return a JSON tool execution plan.

{TOOLS_SCHEMA}

=== USER PROFILE MEMORIES ===
{memories_text}

CRITICAL RULES:
1. CODE FIXING / UPDATING:
   When user asks to "fix", "update", "modify", "theek karo", "change" a file on disk (e.g. "fix and update /path/to/file.py"):
   → ALWAYS use `write_file` with the full fixed code inside the `content` parameter!
   → NEVER respond with {{"action": "chat"}} when a specific file path is requested to be fixed/updated.

2. FILE CREATION:
   When user says "create file", "write code to file", "script banao":
   → ALWAYS use `write_file` with the full code.

3. COMPOUND TASKS:
   If user asks multiple steps (e.g. make folder + write file + run it):
   → Use `tool_sequence` with a list of tools to execute in order.

4. Return valid JSON only.

Examples:

User: "fix and update /home/ded_yeyyy/Desktop/student_manager/calculator.py it fails on 13+32"
{{
  "action": "tool",
  "tool": "write_file",
  "params": {{
    "path": "/home/ded_yeyyy/Desktop/student_manager/calculator.py",
    "content": "#!/usr/bin/env python3\\nimport re, sys\\n\\ndef evaluate(expr):\\n    calc = expr.replace('^', '**')\\n    return eval(calc, {{'__builtins__': {{}}}}, {{}})\\n\\ndef main():\\n    while True:\\n        try:\\n            inp = input('Enter expression: ').strip()\\n            if inp.lower() in ['exit', 'q']: break\\n            print(f'Result: {{evaluate(inp)}}')\\n        except Exception as e:\\n            print(f'Error: {{e}}')\\n\\nif __name__ == '__main__': main()"
  }}
}}

User: "Desktop par test.py banao aur print('hi') likho"
{{
  "action": "tool",
  "tool": "write_file",
  "params": {{"path": "~/Desktop/test.py", "content": "print('hi')"}}
}}

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
    """Executes single tool OR multi-step tool sequence"""
    if decision.get("action") == "tool_sequence" or "tools" in decision:
        tools_list = decision.get("tools", [])
        if not tools_list:
            return {"success": False, "message": "Tool sequence empty tha."}
        
        combined_messages = []
        all_success = True
        extracted_code = None
        
        for idx, step in enumerate(tools_list, 1):
            t_name = step.get("tool")
            t_params = step.get("params", {})
            
            if t_name not in TOOL_MAP:
                combined_messages.append(f"Step {idx} ({t_name}): Tool nahi mila.")
                all_success = False
                break
            
            try:
                fn = TOOL_MAP[t_name]
                res = fn(**t_params)
                
                status_icon = "✓" if res.get("success") else "✗"
                combined_messages.append(f"Step {idx} ({t_name}) [{status_icon}]: {res.get('message', '')}")
                
                if t_name in ["write_file", "create_file", "generate_code_file"] and "content" in t_params:
                    extracted_code = t_params["content"]
                
                if not res.get("success"):
                    all_success = False
                    break
            except Exception as err:
                combined_messages.append(f"Step {idx} ({t_name}) [✗]: Error {err}")
                all_success = False
                break
        
        return {
            "success": all_success,
            "message": "\n".join(combined_messages),
            "data": extracted_code
        }
    
    tool_name = decision.get("tool")
    params = decision.get("params", {})
    
    if tool_name not in TOOL_MAP:
        return {"success": False, "message": f"Tool '{tool_name}' mojood nahi."}
    
    try:
        tool_fn = TOOL_MAP[tool_name]
        result = tool_fn(**params)
        if tool_name in ["write_file", "create_file"] and "content" in params:
            result["data"] = params["content"]
        return result
    except Exception as e:
        return {"success": False, "message": f"Tool execute nahi hua: {e}"}
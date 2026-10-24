"""
Tool Router: LUCIA ka decision brain

Strict rules for file creation, fixing, updating, and execution on disk.
"""

import json
import re

from langchain_core.messages import HumanMessage

from tools import (
    open_website,
    open_google,
    open_youtube,
    search_youtube,
    play_youtube,
    web_search,
    list_directory,
    read_file,
    write_file,
    create_file,
    edit_file,
    delete_file,
    create_directory,
    open_file,
    generate_code_file,
    draft_message,
    search_instagram,
    search_whatsapp,
    execute_command,
    authenticate_gmail,
    fetch_unread_emails,
    summarize_emails,
    read_email,
    search_emails,
    prepare_email,
    send_email,
    create_draft,
    reply_email,
    confirm_last_email,
    cancel_last_email,
)


TOOLS_SCHEMA = """
Available tools:

BROWSER:

1. open_website(url) - Opens ANY website
2. open_google(query) - Opens Google or search
3. open_youtube() - Opens YouTube homepage
4. search_youtube(query) - Search YouTube results
5. play_youtube(query) - DIRECTLY play top video
6. web_search(query) - Live web info search

FILESYSTEM:

7. list_directory(path) - List folder contents
8. read_file(path) - Read file contents
9. write_file(path, content) - Create or OVERWRITE/UPDATE a file
10. create_file(path, content) - Create NEW file
11. edit_file(path, old_text, new_text) - Find & replace in file
12. delete_file(path, confirm) - Delete file
13. create_directory(path) - Create folder
14. open_file(path) - Open/read file

TERMINAL:

15. execute_command(command, cwd) - Run terminal command

CODE:

16. generate_code_file(...) - Generate code file

MESSAGING:

17. draft_message(platform, contact, message)
18. search_instagram(query)
19. search_whatsapp(query)

GMAIL:

20. authenticate_gmail()
21. fetch_unread_emails()
22. summarize_emails()
23. read_email(...)
24. search_emails(...)
25. prepare_email(to, subject, body, cc)
26. send_email(...)
27. create_draft(...)
28. reply_email(...)
29. confirm_last_email()
30. cancel_last_email()
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
    "open_file": open_file,

    "execute_command": execute_command,
    "generate_code_file": generate_code_file,

    "draft_message": draft_message,
    "search_instagram": search_instagram,
    "search_whatsapp": search_whatsapp,

    # Backward-compatible aliases
    "list_files": list_directory,
    "create_folder": create_directory,

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


def normalize_llm_content(content) -> str:
    """
    Converts LangChain/Gemini response content into plain string.

    Handles:
    - normal string
    - list of strings
    - list of dictionaries containing text/content
    - other response types
    """

    if content is None:
        return ""

    if isinstance(content, str):
        return content.strip()

    if isinstance(content, list):
        parts = []

        for item in content:
            if isinstance(item, str):
                parts.append(item)

            elif isinstance(item, dict):
                text_value = item.get("text")

                if text_value:
                    parts.append(str(text_value))
                    continue

                content_value = item.get("content")

                if content_value:
                    if isinstance(content_value, list):
                        parts.append(
                            normalize_llm_content(content_value)
                        )
                    else:
                        parts.append(str(content_value))

            else:
                parts.append(str(item))

        return "\n".join(parts).strip()

    return str(content).strip()


def extract_json_object(text: str) -> str:
    """
    Extract JSON object from plain text or markdown-wrapped response.
    """

    if not text:
        return ""

    text = text.strip()

    # Remove markdown code fences
    text = re.sub(
        r"```(?:json)?",
        "",
        text,
        flags=re.IGNORECASE
    ).strip()

    # Remove closing fence if still present
    text = text.replace("```", "").strip()

    # First try complete object extraction
    start = text.find("{")
    end = text.rfind("}")

    if start != -1 and end != -1 and end > start:
        return text[start:end + 1].strip()

    return text


def decide_action(user_msg: str, llm) -> dict:
    """
    Decide whether the user message requires:
    - direct chat
    - one tool
    - multiple tools
    """

    msg_clean = user_msg.lower().strip()

    # Email confirmation shortcuts
    if msg_clean in [
        "haan bhej do",
        "send kar do",
        "bhej do",
        "bhej de",
        "send it",
        "yes send it",
    ]:
        return {
            "action": "tool",
            "tool": "confirm_last_email",
            "params": {},
        }

    # Email cancellation shortcuts
    if msg_clean in [
        "cancel karo",
        "cancel",
        "mat bhejo",
        "discard",
        "discard it",
    ]:
        return {
            "action": "tool",
            "tool": "cancel_last_email",
            "params": {},
        }

    try:
        # Load global memories
        from database import get_global_memories

        mems = get_global_memories()

        memories_text = "No profile memories found."

        if mems:
            memories_text = "\n".join(
                f"- {m.get('memory', '')}"
                for m in mems
            )

    except Exception:
        memories_text = "No profile memories found."

    router_prompt = f"""
You are LUCIA's action router.

Analyze the user's message and return a valid JSON tool execution plan.

{TOOLS_SCHEMA}

=== USER PROFILE MEMORIES ===

{memories_text}

CRITICAL RULES:

1. CODE FIXING / UPDATING

When the user asks to fix, update, modify, or change a file on disk:

Examples:
- fix this file
- update this Python file
- theek karo
- modify this code
- fix /path/to/file.py

If a specific file path is given:

ALWAYS use write_file with the FULL fixed code
inside the content parameter.

NEVER return action chat for a requested file modification.

2. FILE CREATION

When the user says:
- create file
- write code to file
- script banao
- file bana do

Use write_file with the complete content.

3. COMPOUND TASKS

If the user asks multiple operations:

Example:
- folder banao
- file likho
- phir run karo

Return:

{{
  "action": "tool_sequence",
  "tools": [
    {{
      "tool": "create_directory",
      "params": {{
        "path": "/path/to/folder"
      }}
    }},
    {{
      "tool": "write_file",
      "params": {{
        "path": "/path/to/file.py",
        "content": "complete code"
      }}
    }}
  ]
}}

4. NORMAL CONVERSATION

If no tool is required:

{{
  "action": "chat"
}}

5. Return valid JSON only.
Do not include markdown.
Do not include explanations.

User message:

{user_msg}
"""

    try:
        response = llm.invoke(
            [HumanMessage(content=router_prompt)]
        )

        # FIX: Gemini may return list content instead of string
        text = normalize_llm_content(response.content)

        # Extract clean JSON
        text = extract_json_object(text)

        if not text:
            print("[Router] Empty response from LLM")
            return {"action": "chat"}

        decision = json.loads(text)

        if not isinstance(decision, dict):
            print("[Router] Decision was not a JSON object")
            return {"action": "chat"}

        return decision

    except json.JSONDecodeError as e:
        print(f"[Router JSON Error]: {e}")
        print(f"[Router Raw Output]: {text if 'text' in locals() else 'N/A'}")
        return {"action": "chat"}

    except Exception as e:
        print(f"[Router Error]: {e}")
        return {"action": "chat"}


def execute_tool(decision: dict) -> dict:
    """
    Executes a single tool OR a multi-step tool sequence.
    """

    # Multi-tool sequence
    if (
        decision.get("action") == "tool_sequence"
        or "tools" in decision
    ):
        tools_list = decision.get("tools", [])

        if not tools_list:
            return {
                "success": False,
                "message": "Tool sequence empty tha.",
            }

        combined_messages = []
        all_success = True
        extracted_code = None

        for idx, step in enumerate(tools_list, 1):
            t_name = step.get("tool")
            t_params = step.get("params", {})

            if t_name not in TOOL_MAP:
                combined_messages.append(
                    f"Step {idx} ({t_name}): Tool nahi mila."
                )
                all_success = False
                break

            try:
                fn = TOOL_MAP[t_name]
                result = fn(**t_params)

                if not isinstance(result, dict):
                    result = {
                        "success": True,
                        "message": str(result),
                    }

                status_icon = (
                    "✓"
                    if result.get("success")
                    else "✗"
                )

                combined_messages.append(
                    f"Step {idx} ({t_name}) "
                    f"[{status_icon}]: "
                    f"{result.get('message', '')}"
                )

                if (
                    t_name in [
                        "write_file",
                        "create_file",
                        "generate_code_file",
                    ]
                    and "content" in t_params
                ):
                    extracted_code = t_params["content"]

                if not result.get("success"):
                    all_success = False
                    break

            except Exception as err:
                combined_messages.append(
                    f"Step {idx} ({t_name}) "
                    f"[✗]: Error {err}"
                )
                all_success = False
                break

        return {
            "success": all_success,
            "message": "\n".join(combined_messages),
            "data": extracted_code,
        }

    # Single tool execution
    tool_name = decision.get("tool")
    params = decision.get("params", {})

    if tool_name not in TOOL_MAP:
        return {
            "success": False,
            "message": f"Tool '{tool_name}' mojood nahi.",
        }

    try:
        tool_fn = TOOL_MAP[tool_name]
        result = tool_fn(**params)

        if not isinstance(result, dict):
            result = {
                "success": True,
                "message": str(result),
            }

        if (
            tool_name in ["write_file", "create_file"]
            and "content" in params
        ):
            result["data"] = params["content"]

        return result

    except Exception as e:
        return {
            "success": False,
            "message": f"Tool execute nahi hua: {e}",
        }
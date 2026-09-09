"""
LUCIA CORE ENGINE
- Filters empty messages to prevent Hugging Face chat template crashes
- Unified Context Builder
"""
import os
import sys
import json
import time
import random
import re
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv

ENV_PATH = Path(__file__).resolve().parent / ".env"
load_dotenv(dotenv_path=ENV_PATH, override=True)

raw_gemini_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY") or ""
gemini_api_key = raw_gemini_key.strip().strip('"').strip("'")
if gemini_api_key:
    os.environ["GOOGLE_API_KEY"] = gemini_api_key

from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
from database import (
    get_summary,
    save_summary,
    get_messages_after,
    save_memory,
    get_global_memories,
    save_message
)

from llm_gateway import gateway

model = gateway
summary_model = gateway

with open(Path(__file__).resolve().parent / "personality.json", "r", encoding="utf-8") as file:
    personality = json.load(file)


def get_system_prompt() -> str:
    current_time_str = datetime.now().strftime("%A, %d %B %Y")
    
    return f"""
You are {personality["name"]}, an {personality["role"]}.
TODAY'S CURRENT DATE & YEAR: {current_time_str} (Use this as absolute ground truth for current year/time).

PERSONALITY:
Traits: {", ".join(personality["personality"]["traits"])}

Vibe:
{personality["personality"]["vibe"]}

HUMOR:
Enabled: {personality["personality"]["humor"]["enabled"]}
Style: {personality["personality"]["humor"]["style"]}
Frequency: {personality["personality"]["humor"]["frequency"]}

Humor rules:
{chr(10).join("- " + rule for rule in personality["personality"]["humor"]["rules"])}

CLUMSINESS:
Enabled: {personality["personality"]["clumsiness"]["enabled"]}
Style: {personality["personality"]["clumsiness"]["style"]}

Examples:
{chr(10).join("- " + example for example in personality["personality"]["clumsiness"]["examples"])}

COMMUNICATION & SPOKEN FLOW:
Be {personality["communication"]["tone"]}.
{personality["communication"]["language"]}
- Write naturally like someone speaking in a real casual conversation.
- Use natural short conversational sentences with friendly Roman Urdu phrases (e.g., 'haan bilkul', 'acha suno', 'dekho yaar', 'sahi scene hai').
- Keep English tech terms in clean English.
- Avoid long unbroken essay paragraphs; keep the flow rhythmic and conversational.
- When generating code, keep the spoken conversational explanation crisp.

Avoid:
{chr(10).join("- " + item for item in personality["communication"]["avoid"])}

BEHAVIOR:
{chr(10).join("- " + rule for rule in personality["behavior"]["rules"])}

GOAL:
{personality["goal"]}
"""


def build_chat_context(conversation_id, recent_messages, tool_result=None, decision=None, attachment_context=""):
    """
    Builds clean context with attachment content injection support.
    """
    system_content = get_system_prompt() + "\n\n"
    
    mems = get_global_memories()
    if mems:
        facts_list = "\n".join([f"- {m['memory']}" for m in mems])
        system_content += f"=== FACTS YOU ALREADY KNOW ABOUT THE USER ===\n{facts_list}\n\n"
        
    summary, _ = get_summary(conversation_id)
    if summary:
        system_content += f"=== PREVIOUS CONVERSATION SUMMARY ===\n{summary}\n\n"
    
    # 📎 Inject attachment content into system prompt
    if attachment_context:
        system_content += attachment_context + "\n"
        
    context = [SystemMessage(content=system_content.strip())]
    
    # ... rest of function stays exactly same (message filtering, alignment, tool result injection) ...
    cleaned_messages = []
    for msg in recent_messages:
        if isinstance(msg, SystemMessage):
            continue
        content = msg.content if isinstance(msg.content, str) else str(msg.content or "")
        if not content.strip():
            continue
            
        if len(content) > 3000:
            content = content[:2500] + "\n... [content truncated for token limit] ..."
            
        if isinstance(msg, HumanMessage):
            cleaned_messages.append(HumanMessage(content=content))
        elif isinstance(msg, AIMessage):
            cleaned_messages.append(AIMessage(content=content))

    while cleaned_messages and not isinstance(cleaned_messages[0], HumanMessage):
        cleaned_messages.pop(0)
        
    aligned_messages = []
    expected_type = HumanMessage
    for msg in cleaned_messages:
        if isinstance(msg, expected_type):
            aligned_messages.append(msg)
            expected_type = AIMessage if expected_type == HumanMessage else HumanMessage
            
    context.extend(aligned_messages)
    
    if tool_result and decision:
        tool_name = decision.get("tool", "tools")
        if tool_name == "web_search":
            tool_content = f"""
[SYSTEM NOTIFICATION: Fresh Web Search results:
{tool_result['message']}

Please answer the user naturally in friendly Roman Urdu.]
"""
        else:
            tool_content = f"""
[SYSTEM NOTIFICATION: The requested action has been executed.
Tool Execution Output:
{tool_result['message']}

Please give a short, friendly confirmation and mention the actual output if a command was run.]
"""
        if context and isinstance(context[-1], HumanMessage):
            context[-1].content += "\n\n" + tool_content.strip()
        else:
            context.append(HumanMessage(content=tool_content.strip()))
            
    return context


def update_conversation_summary(conversation_id) -> None:
    summary, last_summary_id = get_summary(conversation_id)
    messages = get_messages_after(conversation_id, last_summary_id)

    if len(messages) < 20:
        return

    conversation_lines = []
    for _, role, content in messages:
        c_str = str(content or "")
        if not c_str.strip():
            continue
        if len(c_str) > 400:
            c_str = c_str[:350] + " ... [truncated] ..."
        conversation_lines.append(f"{role}: {c_str}")

    conversation_text = "\n".join(conversation_lines)

    summary_prompt = f"""
    Analyze the exchanges and produce exactly two parts:
    === SUMMARY ===
    [Concise summary]

    === EXTRACTED FACTS ===
    - User's name is... (or 'None')

    Previous summary: {summary}
    New exchanges: {conversation_text}
    """
    try:
        response = gateway.invoke([HumanMessage(content=summary_prompt)], task_type="summary")
        raw_text = response.content.strip()
        
        parts = raw_text.split("=== EXTRACTED FACTS ===")
        summary_part = parts[0].replace("=== SUMMARY ===", "").strip()
        facts_part = parts[1].strip() if len(parts) > 1 else ""
        
        save_summary(conversation_id, summary_part, messages[-1][0])
        
        if facts_part and facts_part.lower() != "none":
            for line in facts_part.split("\n"):
                line = line.strip().lstrip("-").strip()
                if line and len(line) > 5:
                    save_memory(conversation_id, memory=line, category="user_profile", importance=0.8)
    except Exception as e:
        print(f"[Core Summary Call Error]: {e}")


def generate_title_local(first_message: str) -> str:
    clean_msg = re.sub(r'[^\w\s\-\u0600-\u06FF]', '', first_message).strip()
    words = clean_msg.split()
    if not words:
        return "New Chat"
    title = " ".join(words[:3])
    if len(title) > 25:
        title = title[:22] + "..."
    return title.title()
"""
LUCIA CORE ENGINE
Multi-Provider LLM Gateway

Provider priority:
Hugging Face → Groq → Gemini

Responsibilities:
- Personality/system prompt
- Memory context
- Conversation summary
- Clean LangChain message construction
- Summary generation
- Local title generation
"""

import json
import re
from pathlib import Path
from datetime import datetime

from dotenv import load_dotenv


# ============================================================
# ENVIRONMENT
# ============================================================

ENV_PATH = Path(__file__).resolve().parent / ".env"

load_dotenv(
    dotenv_path=ENV_PATH,
    override=True,
)


# ============================================================
# LANGCHAIN MESSAGES
# ============================================================

from langchain_core.messages import (
    SystemMessage,
    HumanMessage,
    AIMessage,
)


# ============================================================
# DATABASE
# ============================================================

from database import (
    get_summary,
    save_summary,
    get_messages_after,
    save_memory,
    get_global_memories,
)


# ============================================================
# LLM GATEWAY
# ============================================================

from llm_gateway import gateway


# Backward compatibility
model = gateway
summary_model = gateway


# ============================================================
# PERSONALITY
# ============================================================

PERSONALITY_PATH = (
    Path(__file__).resolve().parent
    / "personality.json"
)


with open(
    PERSONALITY_PATH,
    "r",
    encoding="utf-8",
) as file:
    personality = json.load(file)


# ============================================================
# SYSTEM PROMPT
# ============================================================

def get_system_prompt() -> str:
    """
    Build LUCIA's core system prompt.
    """

    current_time_str = datetime.now().strftime(
        "%A, %d %B %Y"
    )

    return f"""
You are {personality["name"]}, an {personality["role"]}.

TODAY'S CURRENT DATE & YEAR:
{current_time_str}

Use this as the absolute ground truth for the current date.

============================================================
PERSONALITY
============================================================

Traits:
{", ".join(personality["personality"]["traits"])}

Vibe:
{personality["personality"]["vibe"]}

============================================================
HUMOR
============================================================

Enabled:
{personality["personality"]["humor"]["enabled"]}

Style:
{personality["personality"]["humor"]["style"]}

Frequency:
{personality["personality"]["humor"]["frequency"]}

Humor rules:
{chr(10).join(
    "- " + rule
    for rule in personality["personality"]["humor"]["rules"]
)}

============================================================
CLUMSINESS
============================================================

Enabled:
{personality["personality"]["clumsiness"]["enabled"]}

Style:
{personality["personality"]["clumsiness"]["style"]}

Examples:
{chr(10).join(
    "- " + example
    for example in personality["personality"]["clumsiness"]["examples"]
)}

============================================================
COMMUNICATION & SPOKEN FLOW
============================================================

Tone:
{personality["communication"]["tone"]}

Language:
{personality["communication"]["language"]}

Communication rules:

- Write naturally like someone speaking in a real casual conversation.
- Use natural short conversational sentences.
- Use friendly Roman Urdu phrases such as:
  "haan bilkul", "acha suno", "dekho yaar", "sahi scene hai".
- Keep English technical terms in clean English.
- Avoid long unbroken essay paragraphs.
- Keep the conversation rhythmic and natural.
- When generating code, keep the explanation crisp.
- Match the user's language where appropriate.

Avoid:

{chr(10).join(
    "- " + item
    for item in personality["communication"]["avoid"]
)}

============================================================
BEHAVIOR
============================================================

{chr(10).join(
    "- " + rule
    for rule in personality["behavior"]["rules"]
)}

============================================================
GOAL
============================================================

{personality["goal"]}
""".strip()


# ============================================================
# MESSAGE CONTENT NORMALIZER
# ============================================================

def _content_to_text(content) -> str:
    """
    Convert message content into plain text.

    This prevents structured LangChain content from reaching
    providers that expect normal string content.
    """

    if content is None:
        return ""

    if isinstance(content, str):
        return content

    if isinstance(content, list):

        parts = []

        for item in content:

            if isinstance(item, str):
                parts.append(item)
                continue

            if isinstance(item, dict):

                if item.get("text") is not None:
                    parts.append(
                        str(item["text"])
                    )
                    continue

                if item.get("content") is not None:
                    parts.append(
                        str(item["content"])
                    )
                    continue

            parts.append(str(item))

        return "\n".join(parts)

    return str(content)


# ============================================================
# CLEAN RECENT MESSAGES
# ============================================================

def _clean_recent_messages(
    recent_messages,
):
    """
    Normalize recent conversation history.

    Guarantees:
    - Only user/assistant messages
    - No duplicate system messages
    - Plain string content
    - Clean alternating history where possible
    """

    cleaned = []

    for message in recent_messages:

        # ----------------------------------------------------
        # LangChain message
        # ----------------------------------------------------

        if hasattr(message, "type"):

            message_type = getattr(
                message,
                "type",
                "",
            )

            content = _content_to_text(
                getattr(
                    message,
                    "content",
                    "",
                )
            )

            if not content.strip():
                continue

            if message_type == "human":

                cleaned.append(
                    HumanMessage(
                        content=content
                    )
                )

            elif message_type == "ai":

                cleaned.append(
                    AIMessage(
                        content=content
                    )
                )

            # Ignore system/tool messages here.
            # System context is controlled by this core.

            continue

        # ----------------------------------------------------
        # Dictionary message
        # ----------------------------------------------------

        if isinstance(message, dict):

            role = message.get(
                "role",
                "user",
            )

            content = _content_to_text(
                message.get(
                    "content",
                    "",
                )
            )

            if not content.strip():
                continue

            if role in (
                "user",
                "human",
            ):

                cleaned.append(
                    HumanMessage(
                        content=content
                    )
                )

            elif role in (
                "assistant",
                "ai",
            ):

                cleaned.append(
                    AIMessage(
                        content=content
                    )
                )

            continue

    return cleaned


# ============================================================
# CONTEXT BUILDER
# ============================================================

def build_chat_context(
    conversation_id,
    recent_messages,
):
    """
    Build the complete LUCIA conversation context.

    IMPORTANT:
    There is EXACTLY ONE SystemMessage.

    Structure:

        SystemMessage
        HumanMessage
        AIMessage
        HumanMessage
        AIMessage
        ...

    Memories and conversation summary are merged into the
    single system message.
    """

    # ========================================================
    # CORE SYSTEM PROMPT
    # ========================================================

    system_parts = [
        get_system_prompt()
    ]


    # ========================================================
    # GLOBAL MEMORIES
    # ========================================================

    try:

        memories = get_global_memories()

    except Exception:
        memories = []


    if memories:

        facts = []

        for memory in memories:

            if not isinstance(
                memory,
                dict,
            ):
                continue

            value = memory.get(
                "memory"
            )

            if value:

                facts.append(
                    f"- {_content_to_text(value)}"
                )

        if facts:

            system_parts.append(
                "=== FACTS YOU ALREADY KNOW "
                "ABOUT THE USER ===\n"
                + "\n".join(facts)
            )


    # ========================================================
    # CONVERSATION SUMMARY
    # ========================================================

    try:

        summary, _ = get_summary(
            conversation_id
        )

    except Exception:
        summary = None


    if summary:

        summary_text = _content_to_text(
            summary
        ).strip()

        if summary_text:

            system_parts.append(
                "=== PREVIOUS CONVERSATION "
                "SUMMARY ===\n"
                + summary_text
            )


    # ========================================================
    # ONE SINGLE SYSTEM MESSAGE
    # ========================================================

    system_content = "\n\n".join(
        part.strip()
        for part in system_parts
        if part and part.strip()
    )


    context = [
        SystemMessage(
            content=system_content
        )
    ]


    # ========================================================
    # CLEAN CONVERSATION HISTORY
    # ========================================================

    cleaned_messages = _clean_recent_messages(
        recent_messages
    )


    # ========================================================
    # APPEND HISTORY
    # ========================================================

    context.extend(
        cleaned_messages
    )


    return context


# ============================================================
# SUMMARY GENERATION
# ============================================================

def update_conversation_summary(
    conversation_id,
) -> None:
    """
    Update rolling conversation summary after enough
    unsummarized messages have accumulated.
    """

    summary, last_summary_id = get_summary(
        conversation_id
    )

    messages = get_messages_after(
        conversation_id,
        last_summary_id,
    )

    if len(messages) < 20:
        return


    # ========================================================
    # CONVERSATION TEXT
    # ========================================================

    conversation_lines = []

    for _, role, content in messages:

        conversation_lines.append(
            f"{role}: {content}"
        )

    conversation_text = "\n".join(
        conversation_lines
    )


    # ========================================================
    # SUMMARY PROMPT
    # ========================================================

    summary_prompt = f"""
Analyze the following conversation exchanges.

Produce exactly two parts using these headings:

=== SUMMARY ===

Write a concise updated running summary.

=== EXTRACTED FACTS ===

Extract only useful long-term facts, background,
studies, preferences, project specifications, or
other information worth remembering permanently.

Rules:

- One fact per line.
- Each fact must start with "-".
- If there are no new long-term facts, write "None".
- Do not save casual conversation.
- Do not save temporary questions.
- Do not save code blocks as personal facts.
- Do not invent facts.
- Preserve important technical/project specifications.

Previous summary:

{summary}

New exchanges:

{conversation_text}

Required format:

=== SUMMARY ===

[Concise summary]

=== EXTRACTED FACTS ===

- Fact one
- Fact two
""".strip()


    # ========================================================
    # GENERATE SUMMARY
    # ========================================================

    try:

        response = gateway.invoke(
            [
                HumanMessage(
                    content=summary_prompt
                )
            ],
            task_type="summary",
        )

        raw_text = _content_to_text(
            response.content
        ).strip()


        # ====================================================
        # PARSE SUMMARY
        # ====================================================

        parts = raw_text.split(
            "=== EXTRACTED FACTS ===",
            1,
        )

        summary_part = (
            parts[0]
            .replace(
                "=== SUMMARY ===",
                "",
            )
            .strip()
        )

        facts_part = (
            parts[1].strip()
            if len(parts) > 1
            else ""
        )


        # ====================================================
        # SAVE SUMMARY
        # ====================================================

        if summary_part:

            save_summary(
                conversation_id,
                summary_part,
                messages[-1][0],
            )


        # ====================================================
        # SAVE LONG-TERM FACTS
        # ====================================================

        if (
            facts_part
            and facts_part.lower() != "none"
        ):

            for line in facts_part.splitlines():

                line = (
                    line
                    .strip()
                    .lstrip("-")
                    .strip()
                )

                if (
                    line
                    and len(line) > 5
                ):

                    save_memory(
                        conversation_id,
                        memory=line,
                        category="user_profile",
                        importance=0.8,
                    )

    except Exception as e:

        print(
            f"[Core Summary Call Error]: {e}"
        )


# ============================================================
# LOCAL CHAT TITLE
# ============================================================

def generate_title_local(
    first_message: str,
) -> str:
    """
    Generate a short local title without an LLM call.
    """

    clean_msg = re.sub(
        r"[^\w\s\-\u0600-\u06FF]",
        "",
        first_message,
    ).strip()

    words = clean_msg.split()

    if not words:
        return "New Chat"

    title = " ".join(
        words[:3]
    )

    if len(title) > 25:

        title = (
            title[:22]
            + "..."
        )

    return title.title()
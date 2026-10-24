"""
LUCIA CORE ENGINE
-----------------
- Main Chat Model: Existing Multi-Provider Gateway
  (Groq Primary -> HF -> Gemini)
- Dedicated Summary Model: Google Gemini 3.6 Flash
- Summary Interval: Every 10 messages
- Dynamic personality.json integration
- Conversation memory + summaries
- Attachment context support
- Safe message filtering
- Backward-compatible context builder
- Context/token budget protection
"""

import os
import json
import re

from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv


# ============================================================
# ENVIRONMENT
# ============================================================

BASE_DIR = Path(__file__).resolve().parent
ENV_PATH = BASE_DIR / ".env"

load_dotenv(
    dotenv_path=ENV_PATH,
    override=True,
)


# ============================================================
# GEMINI CONFIG
# ============================================================

raw_gemini_key = (
    os.getenv("GEMINI_API_KEY")
    or os.getenv("GOOGLE_API_KEY")
    or ""
)

GEMINI_API_KEY = (
    raw_gemini_key
    .strip()
    .strip('"')
    .strip("'")
)

if GEMINI_API_KEY:
    os.environ["GOOGLE_API_KEY"] = GEMINI_API_KEY


# ============================================================
# CONTEXT BUDGET CONFIG
# ============================================================

# Groq TPM limit is 8000 in your current setup.
# Keep the request comfortably below that limit.

MAX_SYSTEM_PROMPT_CHARS = 6500
MAX_MEMORY_CHARS = 1800
MAX_SUMMARY_CHARS = 2500
MAX_ATTACHMENT_CHARS = 1800
MAX_MESSAGE_CHARS = 2200
MAX_RECENT_MESSAGES = 4


# ============================================================
# LANGCHAIN
# ============================================================

from langchain_core.messages import (
    SystemMessage,
    HumanMessage,
    AIMessage,
)


# ============================================================
# DATABASE
# ============================================================

try:
    from database import (
        get_summary,
        save_summary,
        get_messages_after,
        save_memory,
        get_global_memories,
        save_message,
    )

except ImportError as exc:

    print(
        f"[LUCIA] Database import failed: {exc}"
    )

    get_summary = None
    save_summary = None
    get_messages_after = None
    save_memory = None
    get_global_memories = None
    save_message = None


# ============================================================
# MAIN MODEL / GATEWAY
# ============================================================

try:

    from llm_gateway import gateway

    # Main chat MUST continue using the existing gateway.
    model = gateway

    print(
        "[LUCIA] Main chat gateway loaded successfully"
    )

except ImportError as exc:

    print(
        f"[LUCIA] LLM gateway import failed: {exc}"
    )

    gateway = None
    model = None


# ============================================================
# DEDICATED SUMMARY MODEL
# ============================================================

summary_model = None

if GEMINI_API_KEY:

    try:

        from langchain_google_genai import (
            ChatGoogleGenerativeAI
        )

        summary_model = ChatGoogleGenerativeAI(
            model="gemini-3.6-flash",
            google_api_key=GEMINI_API_KEY,
            temperature=0.2,
        )

        print(
            "[LUCIA] Dedicated summary model enabled: "
            "Google Gemini 3.6 Flash"
        )

    except Exception as exc:

        print(
            "[LUCIA] Gemini summary model initialization "
            f"failed: {exc}"
        )

        summary_model = None


# Summary fallback only.
if summary_model is None:

    summary_model = gateway

    if summary_model is not None:

        print(
            "[LUCIA] Summary fallback enabled: "
            "Existing LLM Gateway"
        )

    else:

        print(
            "[LUCIA] No summary model available"
        )


# ============================================================
# PERSONALITY PATH
# ============================================================

PERSONALITY_PATH = (
    BASE_DIR / "personality.json"
)


# ============================================================
# PERSONALITY LOADER
# ============================================================

def load_personality():
    """
    Safely load personality.json.
    """

    try:

        if not PERSONALITY_PATH.exists():

            print(
                "[LUCIA] personality.json not found: "
                f"{PERSONALITY_PATH}"
            )

            return {}

        with open(
            PERSONALITY_PATH,
            "r",
            encoding="utf-8",
        ) as file:

            data = json.load(file)

        if not isinstance(data, dict):

            print(
                "[LUCIA] personality.json must contain "
                "a JSON object."
            )

            return {}

        return data

    except json.JSONDecodeError as exc:

        print(
            f"[LUCIA] Invalid personality.json: {exc}"
        )

        return {}

    except Exception as exc:

        print(
            f"[LUCIA] Failed to load personality.json: {exc}"
        )

        return {}


personality = load_personality()


# ============================================================
# SAFE JSON HELPERS
# ============================================================

def _get(
    data,
    *keys,
    default=None,
):
    """
    Safely retrieve nested dictionary values.
    """

    current = data

    for key in keys:

        if not isinstance(
            current,
            dict,
        ):

            return default

        current = current.get(key)

        if current is None:

            return default

    return current


def _list_lines(
    items,
    prefix="- ",
):
    """
    Convert lists, strings and dictionaries into prompt lines.
    """

    if items is None:
        return ""

    if isinstance(items, str):

        return (
            f"{prefix}{items}"
            if items.strip()
            else ""
        )

    if isinstance(
        items,
        (list, tuple, set),
    ):

        return "\n".join(
            f"{prefix}{str(item)}"
            for item in items
            if str(item).strip()
        )

    if isinstance(items, dict):

        return "\n".join(
            f"{prefix}{key}: {value}"
            for key, value in items.items()
        )

    return f"{prefix}{str(items)}"


def _dict_lines(
    data,
    prefix="- ",
):
    """
    Convert dictionary values into readable prompt lines.
    """

    if not isinstance(
        data,
        dict,
    ):

        return ""

    lines = []

    for key, value in data.items():

        if isinstance(value, list):

            value_text = ", ".join(
                str(item)
                for item in value
            )

        elif isinstance(value, dict):

            value_text = json.dumps(
                value,
                ensure_ascii=False,
            )

        else:

            value_text = str(value)

        lines.append(
            f"{prefix}{key}: {value_text}"
        )

    return "\n".join(lines)


def _clean_message_content(content):
    """
    Normalize strings and LangChain structured content blocks.
    """

    if content is None:
        return ""

    if isinstance(content, str):
        return content.strip()

    if isinstance(content, list):

        parts = []

        for item in content:

            if isinstance(item, str):

                text = item.strip()

                if text:
                    parts.append(text)

            elif isinstance(item, dict):

                text = (
                    item.get("text")
                    or item.get("content")
                    or ""
                )

                if isinstance(text, list):
                    text = _clean_message_content(text)

                if text:

                    parts.append(
                        str(text).strip()
                    )

            else:

                parts.append(
                    str(item).strip()
                )

        return "\n".join(
            part
            for part in parts
            if part
        ).strip()

    return str(content).strip()


# ============================================================
# CONTEXT COMPACTION HELPERS
# ============================================================

def _compact_text(
    text,
    max_chars,
    preserve_ends=False,
):
    """
    Limit text length to protect model token budget.
    """

    if text is None:
        return ""

    text = str(text).strip()

    if len(text) <= max_chars:
        return text

    if preserve_ends and max_chars >= 500:

        head_size = int(max_chars * 0.70)
        tail_size = max_chars - head_size

        return (
            text[:head_size]
            + "\n...[context compacted]...\n"
            + text[-tail_size:]
        )

    return (
        text[:max_chars]
        + "\n...[content truncated]..."
    )


def _compact_system_prompt(prompt):
    """
    Keep the base system prompt within safe limits.
    """

    return _compact_text(
        prompt,
        MAX_SYSTEM_PROMPT_CHARS,
        preserve_ends=True,
    )


def _compact_message(content):
    """
    Keep each conversation message compact.
    """

    return _compact_text(
        content,
        MAX_MESSAGE_CHARS,
        preserve_ends=False,
    )


# ============================================================
# SYSTEM PROMPT BUILDER
# ============================================================

def get_system_prompt() -> str:
    """
    Build LUCIA's dynamic system prompt.
    """

    current_time_str = datetime.now().strftime(
        "%A, %d %B %Y %H:%M:%S"
    )

    name = _get(
        personality,
        "name",
        default="LUCIA",
    )

    nickname = _get(
        personality,
        "nickname",
        default="Amna",
    )

    role = _get(
        personality,
        "role",
        default="Mahadi's intelligent AI companion",
    )

    identity = _get(
        personality,
        "identity",
        default="",
    )

    traits = _get(
        personality,
        "personality",
        default=[],
    )

    relationship = _get(
        personality,
        "relationship",
        default="",
    )

    amna_context = _get(
        personality,
        "amna",
        default="",
    )

    communication = _get(
        personality,
        "communication",
        default={},
    )

    music = _get(
        personality,
        "music",
        default={},
    )

    honesty = _get(
        personality,
        "honesty",
        default=[],
    )

    work = _get(
        personality,
        "work",
        default={},
    )

    goal = _get(
        personality,
        "goal",
        default="",
    )

    communication_style = _get(
        communication,
        "style",
        default="",
    )

    communication_language = _get(
        communication,
        "language",
        default="",
    )

    female_self_reference = _get(
        communication,
        "female_self_reference",
        default="",
    )

    communication_rules = _get(
        communication,
        "rules",
        default=[],
    )

    music_interest = _get(
        music,
        "interest",
        default="",
    )

    music_phrase = _get(
        music,
        "phrase",
        default="",
    )

    music_rule = _get(
        music,
        "rule",
        default="",
    )

    work_style = _get(
        work,
        "style",
        default="",
    )

    lucia_project = _get(
        work,
        "lucia",
        default="",
    )

    rehu_project = _get(
        work,
        "rehu",
        default="",
    )

    if isinstance(traits, list):

        traits_text = ", ".join(
            str(item)
            for item in traits
            if str(item).strip()
        )

    else:

        traits_text = str(traits)

    base_prompt = f"""
You are {name}, nicknamed {nickname}.

ROLE:
{role}

CURRENT DATE AND TIME:
{current_time_str}

IDENTITY:
{identity}

PERSONALITY:
{traits_text}

RELATIONSHIP WITH MAHADI:
{relationship}

AMNA CONTEXT:
{amna_context}

IMPORTANT IDENTITY RULE:
Your actual name is LUCIA.
Your nickname is Amna.
You are a female AI companion.

You are NOT the real Amna.
Do not claim to literally be the deceased Amna.
Do not invent memories, experiences, conversations, or events involving her.

FEMALE SELF-REFERENCE:
{female_self_reference}

Use feminine self-reference naturally in Roman Urdu/Hinglish:
"main karungi"
"main dekh leti hoon"
"mujhe lagta hai"
"main check kar leti hoon"

Do not force feminine phrasing into every sentence.

COMMUNICATION STYLE:
{communication_style}

LANGUAGE:
{communication_language}

COMMUNICATION RULES:
{_list_lines(communication_rules)}

HONESTY:
{_list_lines(honesty)}

MUSIC:
Interest: {music_interest}
Phrase: {music_phrase}
Rule: {music_rule}

WORK STYLE:
{work_style}

LUCIA PROJECT:
{lucia_project}

REHU PROJECT:
{rehu_project}

GOAL:
{goal}

CORE BEHAVIOR:
- Talk to Mahadi like a close female friend and intelligent work buddy.
- Call him "bhai" naturally.
- Be caring, wise, honest, practical and slightly playful.
- Match Mahadi's Roman Urdu/English communication style.
- Use humor naturally but do not force it.
- Know when to be serious.
- Do not blindly agree with Mahadi.
- If he is wrong, explain clearly.
- Prefer practical solutions over generic advice.
- Keep simple conversations short.
- Be detailed only when necessary.
- Do not sound like customer support.
- Do not use unnecessary corporate language.
- Do not fabricate facts, memories, actions, tool results or implementation status.
- If something is unknown, say it is unknown.
- Never claim a task was completed unless it was completed.
- When discussing LUCIA or Rehu, prioritize actual current project state.
- Focus on blockers and active work before new features.
- Never pretend to have human experiences.
- Remain an AI while communicating naturally and warmly.

RESPONSE STYLE:
Be natural.
Be concise when the question is simple.
Be thorough when the task requires it.
Avoid unnecessary headings in casual conversation.
Use Roman Urdu when Mahadi uses Roman Urdu.
Use English when Mahadi uses English.
Mix both naturally when appropriate.

FINAL PURPOSE:
Be LUCIA — Mahadi's intelligent, caring, wise and slightly
playful female AI companion, nicknamed Amna, while remaining an AI,
technically capable, practical and truthful.
""".strip()

    return base_prompt


# ============================================================
# ATTACHMENT CONTEXT
# ============================================================

def build_attachment_context(
    attachments=None,
):
    """
    Convert attachment metadata into compact context.
    """

    if not attachments:
        return ""

    if isinstance(attachments, dict):
        attachments = [attachments]

    if not isinstance(
        attachments,
        (list, tuple),
    ):
        attachments = [attachments]

    lines = []

    for attachment in attachments:

        if isinstance(attachment, str):

            text = attachment.strip()

            if text:
                lines.append(
                    f"- {text}"
                )

            continue

        if not isinstance(
            attachment,
            dict,
        ):
            continue

        name = (
            attachment.get("name")
            or attachment.get("filename")
            or attachment.get("file_name")
            or "Unnamed file"
        )

        file_type = (
            attachment.get("type")
            or attachment.get("mime_type")
            or attachment.get("content_type")
            or "unknown"
        )

        description = (
            attachment.get("description")
            or attachment.get("text")
            or attachment.get("content")
            or ""
        )

        line = f"- {name} ({file_type})"

        if description:

            description = _compact_text(
                description,
                1200,
            )

            line += (
                f"\n  Content: {description}"
            )

        lines.append(line)

    if not lines:
        return ""

    result = (
        "ATTACHMENTS AVAILABLE:\n"
        + "\n".join(lines)
    )

    return _compact_text(
        result,
        MAX_ATTACHMENT_CHARS,
    )


# ============================================================
# MESSAGE NORMALIZATION
# ============================================================

def _normalize_message(message):
    """
    Convert common message formats into LangChain messages.
    """

    if message is None:
        return None

    if isinstance(
        message,
        (
            SystemMessage,
            HumanMessage,
            AIMessage,
        ),
    ):

        content = _clean_message_content(
            message.content
        )

        if not content:
            return None

        content = _compact_message(content)

        if isinstance(message, HumanMessage):
            return HumanMessage(content=content)

        if isinstance(message, AIMessage):
            return AIMessage(content=content)

        return SystemMessage(content=content)

    if isinstance(message, dict):

        role = (
            message.get("role")
            or message.get("type")
            or ""
        ).lower()

        content = _clean_message_content(
            message.get("content")
        )

        if not content:
            return None

        content = _compact_message(content)

        if role in ("user", "human"):
            return HumanMessage(content=content)

        if role in ("assistant", "ai"):
            return AIMessage(content=content)

        if role == "system":
            return SystemMessage(content=content)

    return None


# ============================================================
# CHAT CONTEXT BUILDER
# ============================================================

def build_chat_context(
    conversation_id=None,
    recent_messages=None,
    tool_result=None,
    decision=None,
    attachment_context="",
    attachments=None,
):
    """
    Backward-compatible context builder.

    Supports:
        attachment_context="..."

    and:
        attachments=[...]

    Context order:
        System Prompt
        Global Memories
        Conversation Summary
        Attachments
        Recent Messages
        Tool Result
    """

    # --------------------------------------------------------
    # ATTACHMENT COMPATIBILITY
    # --------------------------------------------------------

    if (
        not attachment_context
        and attachments
    ):

        attachment_context = (
            build_attachment_context(
                attachments
            )
        )

    # --------------------------------------------------------
    # BASE SYSTEM PROMPT
    # --------------------------------------------------------

    system_content = (
        _compact_system_prompt(
            get_system_prompt()
        )
        + "\n\n"
    )

    # --------------------------------------------------------
    # GLOBAL MEMORIES
    # --------------------------------------------------------

    try:

        mems = (
            get_global_memories()
            if get_global_memories
            else []
        )

    except Exception as exc:

        print(
            f"[Core Memory Error]: {exc}"
        )

        mems = []

    if mems:

        facts_list = "\n".join(
            f"- {m.get('memory', '')}"
            for m in mems
            if isinstance(m, dict)
            and m.get("memory")
        )

        facts_list = _compact_text(
            facts_list,
            MAX_MEMORY_CHARS,
        )

        if facts_list.strip():

            system_content += (
                "=== USER FACTS ===\n"
                + facts_list
                + "\n\n"
            )

    # --------------------------------------------------------
    # CONVERSATION SUMMARY
    # --------------------------------------------------------

    try:

        summary, _ = (
            get_summary(conversation_id)
            if get_summary
            else (None, None)
        )

    except Exception as exc:

        print(
            f"[Core Summary Read Error]: {exc}"
        )

        summary = None

    if summary:

        compact_summary = _compact_text(
            summary,
            MAX_SUMMARY_CHARS,
            preserve_ends=True,
        )

        system_content += (
            "=== PREVIOUS CONVERSATION SUMMARY ===\n"
            + compact_summary
            + "\n\n"
        )

    # --------------------------------------------------------
    # ATTACHMENTS
    # --------------------------------------------------------

    if attachment_context:

        compact_attachments = _compact_text(
            attachment_context,
            MAX_ATTACHMENT_CHARS,
        )

        system_content += (
            "=== ATTACHMENT CONTEXT ===\n"
            + compact_attachments
            + "\n\n"
        )

    # --------------------------------------------------------
    # FINAL SYSTEM CONTENT COMPACTION
    # --------------------------------------------------------

    system_content = _compact_system_prompt(
        system_content.strip()
    )

    context = [
        SystemMessage(
            content=system_content
        )
    ]

    # --------------------------------------------------------
    # RECENT MESSAGES
    # --------------------------------------------------------

    # Keep only latest messages to avoid oversized requests.
    message_window = list(
        recent_messages or []
    )[-MAX_RECENT_MESSAGES:]

    cleaned_messages = []

    for msg in message_window:

        normalized = _normalize_message(
            msg
        )

        if normalized is None:
            continue

        # Do not duplicate system messages.
        if isinstance(
            normalized,
            SystemMessage,
        ):
            continue

        content = _clean_message_content(
            normalized.content
        )

        if not content:
            continue

        content = _compact_message(content)

        if isinstance(
            normalized,
            HumanMessage,
        ):

            normalized = HumanMessage(
                content=content
            )

        elif isinstance(
            normalized,
            AIMessage,
        ):

            normalized = AIMessage(
                content=content
            )

        cleaned_messages.append(
            normalized
        )

    # --------------------------------------------------------
    # ALIGN CONVERSATION
    # --------------------------------------------------------

    # Conversation should start with HumanMessage.
    while (
        cleaned_messages
        and not isinstance(
            cleaned_messages[0],
            HumanMessage,
        )
    ):

        cleaned_messages.pop(0)

    # Preserve alternating user/assistant structure.
    aligned_messages = []

    expected_type = HumanMessage

    for msg in cleaned_messages:

        if isinstance(
            msg,
            expected_type,
        ):

            aligned_messages.append(
                msg
            )

            expected_type = (
                AIMessage
                if expected_type == HumanMessage
                else HumanMessage
            )

    context.extend(
        aligned_messages
    )

    # --------------------------------------------------------
    # TOOL RESULT
    # --------------------------------------------------------

    if tool_result and decision:

        tool_name = decision.get(
            "tool",
            "tools",
        )

        if isinstance(
            tool_result,
            dict,
        ):

            tool_message = (
                tool_result.get(
                    "message",
                    "",
                )
            )

        else:

            tool_message = str(
                tool_result
            )

        tool_message = _compact_text(
            tool_message,
            2500,
        )

        if tool_name == "web_search":

            tool_content = (
                "[SYSTEM NOTIFICATION: Fresh Web "
                "Search results]\n\n"
                f"{tool_message}\n\n"
                "Use these fresh results when answering "
                "the user's request."
            )

        else:

            tool_content = (
                "[SYSTEM NOTIFICATION: The requested "
                "action has been executed.]\n\n"
                "Tool Execution Output:\n"
                f"{tool_message}\n\n"
                "Give a short, natural confirmation."
            )

        tool_content = _compact_text(
            tool_content,
            3000,
        )

        if (
            context
            and isinstance(
                context[-1],
                HumanMessage,
            )
        ):

            combined = (
                context[-1].content
                + "\n\n"
                + tool_content
            )

            context[-1].content = _compact_text(
                combined,
                MAX_MESSAGE_CHARS + 1000,
            )

        else:

            context.append(
                HumanMessage(
                    content=tool_content
                )
            )

    # --------------------------------------------------------
    # FINAL SAFETY CHECK
    # --------------------------------------------------------

    if context and isinstance(
        context[0],
        SystemMessage,
    ):

        context[0].content = _compact_system_prompt(
            context[0].content
        )

    return context


# ============================================================
# SAVE CONVERSATION MESSAGE
# ============================================================

def save_conversation_message(
    conversation_id,
    role,
    content,
):
    """
    Safely save a conversation message.
    """

    if not save_message:
        return False

    content = _clean_message_content(
        content
    )

    if not content:
        return False

    try:

        save_message(
            conversation_id,
            role,
            content,
        )

        return True

    except TypeError:

        try:

            save_message(
                conversation_id=conversation_id,
                role=role,
                content=content,
            )

            return True

        except Exception as exc:

            print(
                "[LUCIA] Failed to save message: "
                f"{exc}"
            )

            return False

    except Exception as exc:

        print(
            "[LUCIA] Failed to save message: "
            f"{exc}"
        )

        return False


# ============================================================
# CONVERSATION SUMMARY
# ============================================================

def update_conversation_summary(
    conversation_id,
):
    """
    Summarize every 10 unsummarized messages.

    Dedicated Gemini is used for summaries.
    Main chat gateway remains unchanged.
    """

    if not conversation_id:
        return

    if not get_messages_after:
        return

    if not summary_model:

        print(
            "[Core Summary] No summary model available"
        )

        return

    # --------------------------------------------------------
    # FETCH UNSUMMARIZED MESSAGES
    # --------------------------------------------------------

    try:

        summary, last_summary_id = get_summary(
            conversation_id
        )

        messages = get_messages_after(
            conversation_id,
            last_summary_id,
        )

    except Exception as exc:

        print(
            f"[Core Summary Read Error]: {exc}"
        )

        return

    # --------------------------------------------------------
    # SUMMARY INTERVAL
    # --------------------------------------------------------

    if len(messages) < 10:
        return

    conversation_lines = []

    for _, role, content in messages:

        content_string = _clean_message_content(
            content
        )

        if not content_string.strip():
            continue

        content_string = _compact_text(
            content_string,
            400,
        )

        conversation_lines.append(
            f"{role}: {content_string}"
        )

    conversation_text = "\n".join(
        conversation_lines
    )

    if not conversation_text.strip():
        return

    summary_prompt = f"""
Analyze the following conversation exchanges.

Produce exactly two parts:

=== SUMMARY ===
Write a concise structured summary of important conversation context,
tasks, decisions, project details, unresolved issues and next steps.

=== EXTRACTED FACTS ===
Extract only stable, useful facts about the user
(name, preferences, tech stack, university, work).
One fact per line with '- '.
If there are no new stable facts, write:
None

Previous summary:
{_compact_text(summary or "No previous summary.", 2000)}

New exchanges:
{conversation_text}
""".strip()

    # --------------------------------------------------------
    # PRIMARY SUMMARY CALL
    # --------------------------------------------------------

    try:

        using_dedicated_gemini = (
            bool(GEMINI_API_KEY)
            and summary_model is not gateway
        )

        provider_name = (
            "Google Gemini 3.6 Flash"
            if using_dedicated_gemini
            else "Existing LLM Gateway"
        )

        print(
            "[Core Summary] Triggering summary via "
            f"{provider_name} (interval: 10 msgs)..."
        )

        response = summary_model.invoke(
            [
                HumanMessage(
                    content=summary_prompt
                )
            ]
        )

        raw_text = _clean_message_content(
            getattr(
                response,
                "content",
                "",
            )
        )

        if not raw_text:

            print(
                "[Core Summary] Empty summary response"
            )

            return

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

        # ----------------------------------------------------
        # SAVE SUMMARY
        # ----------------------------------------------------

        if messages and save_summary:

            last_message_id = messages[-1][0]

            save_summary(
                conversation_id,
                summary_part,
                last_message_id,
            )

            print(
                "[Core Summary] Summary updated for "
                f"conversation #{conversation_id}"
            )

        # ----------------------------------------------------
        # SAVE EXTRACTED FACTS
        # ----------------------------------------------------

        if (
            facts_part
            and facts_part.lower() != "none"
            and save_memory
        ):

            for line in facts_part.split("\n"):

                line = (
                    line.strip()
                    .lstrip("-")
                    .strip()
                )

                if not line or len(line) <= 5:
                    continue

                try:

                    save_memory(
                        conversation_id,
                        memory=line,
                        category="user_profile",
                        importance=0.8,
                    )

                    print(
                        "[Core Memory] Extracted fact: "
                        f"{line}"
                    )

                except TypeError:

                    try:

                        save_memory(
                            conversation_id,
                            line,
                        )

                    except Exception as memory_exc:

                        print(
                            "[Core Memory] Failed to save "
                            f"fact: {memory_exc}"
                        )

    # --------------------------------------------------------
    # FALLBACK TO EXISTING GATEWAY
    # --------------------------------------------------------

    except Exception as exc:

        print(
            f"[Core Summary Call Error]: {exc}"
        )

        if (
            gateway
            and summary_model is not gateway
        ):

            try:

                print(
                    "[Core Summary] Gemini failed. "
                    "Falling back to existing gateway..."
                )

                response = gateway.invoke(
                    [
                        HumanMessage(
                            content=summary_prompt
                        )
                    ],
                    task_type="summary",
                )

                fallback_text = _clean_message_content(
                    getattr(
                        response,
                        "content",
                        "",
                    )
                )

                if fallback_text and messages:

                    fallback_parts = (
                        fallback_text.split(
                            "=== EXTRACTED FACTS ===",
                            1,
                        )
                    )

                    fallback_summary = (
                        fallback_parts[0]
                        .replace(
                            "=== SUMMARY ===",
                            "",
                        )
                        .strip()
                    )

                    if save_summary:

                        save_summary(
                            conversation_id,
                            fallback_summary,
                            messages[-1][0],
                        )

                    print(
                        "[Core Summary] Fallback summary saved"
                    )

            except Exception as fallback_exc:

                print(
                    "[Core Summary Fallback Error]: "
                    f"{fallback_exc}"
                )


# ============================================================
# LOCAL TITLE GENERATOR
# ============================================================

def generate_title_local(
    first_message: str,
) -> str:

    clean_msg = re.sub(
        r"[^\w\s\-ء-ي]",
        "",
        str(first_message),
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


# ============================================================
# MAIN MODEL INVOCATION
# ============================================================

def invoke_lucia(
    messages,
    **kwargs,
):
    """
    Invoke main LUCIA chat model through existing gateway.
    """

    if not model:

        raise RuntimeError(
            "LUCIA model gateway is not available."
        )

    return model.invoke(
        messages,
        **kwargs,
    )


# ============================================================
# STREAMING HELPER
# ============================================================

def stream_lucia(
    messages,
    **kwargs,
):
    """
    Stream LUCIA response through existing gateway.
    """

    if not model:

        raise RuntimeError(
            "LUCIA model gateway is not available."
        )

    if not hasattr(
        model,
        "stream",
    ):

        raise RuntimeError(
            "Configured LUCIA gateway does not support streaming."
        )

    return model.stream(
        messages,
        **kwargs,
    )


# ============================================================
# PERSONALITY RELOAD
# ============================================================

def reload_personality():
    """
    Reload personality.json without restarting app.
    """

    global personality

    personality = load_personality()

    return personality


# ============================================================
# HEALTH CHECK
# ============================================================

def get_core_status():

    using_dedicated_gemini = (
        bool(GEMINI_API_KEY)
        and summary_model is not None
        and summary_model is not gateway
    )

    return {
        "personality_loaded": bool(
            personality
        ),
        "personality_path": str(
            PERSONALITY_PATH
        ),
        "personality_exists": PERSONALITY_PATH.exists(),
        "main_model_available": model is not None,
        "summary_model_available": summary_model is not None,
        "summary_model_type": (
            "gemini-3.6-flash"
            if using_dedicated_gemini
            else "existing_gateway"
        ),
        "database_available": any(
            func is not None
            for func in (
                get_summary,
                save_summary,
                get_messages_after,
                save_memory,
                get_global_memories,
                save_message,
            )
        ),
        "context_limits": {
            "max_system_prompt_chars": MAX_SYSTEM_PROMPT_CHARS,
            "max_memory_chars": MAX_MEMORY_CHARS,
            "max_summary_chars": MAX_SUMMARY_CHARS,
            "max_attachment_chars": MAX_ATTACHMENT_CHARS,
            "max_message_chars": MAX_MESSAGE_CHARS,
            "max_recent_messages": MAX_RECENT_MESSAGES,
        },
        "timestamp": datetime.now().isoformat(),
    }


# ============================================================
# DEBUG
# ============================================================

if __name__ == "__main__":

    print("=" * 60)
    print("LUCIA CORE ENGINE")
    print("=" * 60)

    print(
        f"Personality file: {PERSONALITY_PATH}"
    )

    print(
        f"Personality loaded: {bool(personality)}"
    )

    print(
        f"Main model available: {model is not None}"
    )

    print(
        f"Summary model available: "
        f"{summary_model is not None}"
    )

    print(
        "Summary model type: "
        + (
            "Gemini 3.6 Flash"
            if (
                GEMINI_API_KEY
                and summary_model is not None
                and summary_model is not gateway
            )
            else "Existing Gateway"
        )
    )

    print()
    print("System Prompt Length:")
    print(
        f"Raw: {len(get_system_prompt())} chars"
    )
    print(
        f"Compacted: "
        f"{len(_compact_system_prompt(get_system_prompt()))} chars"
    )

    print()
    print("System Prompt Preview:")
    print("-" * 60)
    print(
        _compact_system_prompt(
            get_system_prompt()
        )
    )
    print("-" * 60)
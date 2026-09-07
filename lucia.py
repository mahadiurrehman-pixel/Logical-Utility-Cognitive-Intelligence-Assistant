import streamlit as st
from dotenv import load_dotenv
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
from tools.messaging_tools import confirm_and_send, cancel_message, edit_message
from tool_router import decide_action, execute_tool
from database import (
    create_conversation,
    get_all_conversations,
    update_conversation_title,
    delete_conversation,
    save_message,
    get_messages,
    get_recent_messages,
    delete_last_assistant_message,
    get_summary,
    get_all_memories,
    get_global_memories,
)
from audio_engine import transcribe_audio, synthesize_google_tts

# Core Import
from lucia_core import (
    model,
    summary_model,
    build_chat_context,
    update_conversation_summary,
    generate_title_local,
    get_system_prompt
)

load_dotenv()

st.set_page_config(
    page_title="LUCIA",
    page_icon="🤖",
    layout="wide"
)


def load_conversation(conversation_id):
    st.session_state.current_conversation_id = conversation_id
    summary, _ = get_summary(conversation_id)
    st.session_state.conversation_summary = summary
    st.session_state.current_audio = None
    st.session_state.pending_draft = None

    recent_messages = get_recent_messages(conversation_id, limit=15)
    st.session_state.messages = []
    for role, content in recent_messages:
        if role == "user":
            st.session_state.messages.append(HumanMessage(content=content))
        elif role == "assistant":
            st.session_state.messages.append(AIMessage(content=content))


def stream_response(context):
    try:
        for chunk in model.stream(context):
            content = chunk.content
            if content:
                if isinstance(content, list):
                    for item in content:
                        if isinstance(item, dict) and "text" in item:
                            yield str(item["text"])
                        elif isinstance(item, str):
                            yield item
                else:
                    yield str(content)
    except Exception as e:
        st.error(f"⚠️ API Notice: {e}")


# State Init
if "current_conversation_id" not in st.session_state:
    conversations = get_all_conversations()
    if conversations:
        load_conversation(conversations[0][0])
    else:
        new_id = create_conversation()
        load_conversation(new_id)

if "regenerate_flag" not in st.session_state:
    st.session_state.regenerate_flag = False

if "current_audio" not in st.session_state:
    st.session_state.current_audio = None

if "pending_draft" not in st.session_state:
    st.session_state.pending_draft = None


# SIDEBAR
with st.sidebar:
    st.title("🤖 LUCIA")
    
    st.markdown("### 🎙️ Audio Settings")
    enable_voice_out = st.toggle("🔊 Speak Answers", value=True)

    st.markdown("---")
    if st.button("➕ New Chat", use_container_width=True):
        new_id = create_conversation()
        load_conversation(new_id)
        st.rerun()

    st.markdown("---")
    st.subheader("💬 Conversations")
    conversations = get_all_conversations()
    for conv_id, title, _ in conversations:
        col1, col2 = st.columns([5, 1])
        with col1:
            is_active = (conv_id == st.session_state.current_conversation_id)
            btn_label = f"🟢 {title}" if is_active else f"📄 {title}"
            if st.button(btn_label, key=f"sel_{conv_id}", use_container_width=True):
                load_conversation(conv_id)
                st.rerun()
        with col2:
            if st.button("🗑️", key=f"del_{conv_id}", help="Delete chat"):
                delete_conversation(conv_id)
                if conv_id == st.session_state.current_conversation_id:
                    remaining = get_all_conversations()
                    if remaining:
                        load_conversation(remaining[0][0])
                    else:
                        new_id = create_conversation()
                        load_conversation(new_id)
                st.rerun()

    st.markdown("---")
    st.subheader("🧠 Long-term Memories")
    mems = get_global_memories()
    if mems:
        for m in mems:
            st.markdown(f"📌 {m['memory']}")
    else:
        st.caption("No profile facts stored yet.")


# MAIN CHAT VIEW
st.title("LUCIA")
st.caption("Your intelligent work companion")

# Display Chat History
for idx, message in enumerate(st.session_state.messages):
    if isinstance(message, HumanMessage):
        with st.chat_message("user"):
            st.write(message.content)
    elif isinstance(message, AIMessage):
        with st.chat_message("assistant"):
            st.write(message.content)
            
            if idx == len(st.session_state.messages) - 1:
                if st.session_state.current_audio and enable_voice_out:
                    st.audio(st.session_state.current_audio, format="audio/mp3", autoplay=True)

                if st.button("↻ Regenerate", key=f"regen_{idx}"):
                    st.session_state.messages.pop()
                    delete_last_assistant_message(st.session_state.current_conversation_id)
                    st.session_state.current_audio = None
                    st.session_state.regenerate_flag = True
                    st.rerun()


# ==========================================
# 📩 UNIFIED MESSAGE & EMAIL DRAFT UI
# ==========================================
if st.session_state.pending_draft:
    draft = st.session_state.pending_draft
    is_gmail = (draft.get("platform") == "gmail")
    
    with st.chat_message("assistant"):
        st.markdown(f"### 📩 { 'Email Draft' if is_gmail else 'Message Draft' }")
        col_a, col_b = st.columns(2)
        with col_a:
            st.markdown(f"**Platform:** `{draft['platform'].title()}`")
        with col_b:
            st.markdown(f"**To:** `{draft['contact_name'].title() if is_gmail else draft['contact_name'].title()}`")
            
        if is_gmail:
            st.markdown(f"**Subject:** `{draft['subject']}`")
        
        edited_msg = st.text_area(
            "**Message Body:**", 
            value=draft['message'], 
            key=f"edit_{draft['id']}",
            height=100
        )
        
        col1, col2, col3 = st.columns([1, 1, 1])
        
        with col1:
            if st.button("✅ Send", key=f"send_{draft['id']}", use_container_width=True, type="primary"):
                draft['message'] = edited_msg
                with st.spinner("📤 Sending..."):
                    if is_gmail:
                        from tools.gmail_tools import send_email
                        result = send_email(
                            to=draft.get("to") or draft.get("contact_id"),
                            subject=draft.get("subject"),
                            body=draft['message'],
                            cc=draft.get("cc", ""),
                            confirm=True
                        )
                    else:
                        result = confirm_and_send(draft)
                
                confirmation = f"{'✅' if result['success'] else '❌'} {result['message']}"
                st.session_state.messages.append(AIMessage(content=confirmation))
                save_message(st.session_state.current_conversation_id, "assistant", confirmation)
                st.session_state.pending_draft = None
                st.rerun()
        
        with col2:
            if st.button("✏️ Update", key=f"update_{draft['id']}", use_container_width=True):
                draft['message'] = edited_msg
                st.session_state.pending_draft = draft
                st.success("Draft update kar diya!")
                st.rerun()
        
        with col3:
            if st.button("❌ Cancel", key=f"cancel_{draft['id']}", use_container_width=True):
                st.session_state.pending_draft = None
                cancellation = "❌ Email draft cancel kar diya." if is_gmail else "❌ Message cancel kar diya."
                st.session_state.messages.append(AIMessage(content=cancellation))
                save_message(st.session_state.current_conversation_id, "assistant", cancellation)
                st.rerun()


# REGENERATE FLOW
if st.session_state.regenerate_flag:
    st.session_state.regenerate_flag = False
    context = build_chat_context(st.session_state.current_conversation_id, st.session_state.messages[-6:])
    
    with st.chat_message("assistant"):
        try:
            raw_res = st.write_stream(stream_response(context))
            response_text = str(raw_res) if raw_res is not None else ""
            
            if response_text.strip():
                if enable_voice_out:
                    with st.spinner("🔊 Generating voice..."):
                        audio_bytes = synthesize_google_tts(response_text)
                        st.session_state.current_audio = audio_bytes
                
                st.session_state.messages.append(AIMessage(content=response_text))
                save_message(st.session_state.current_conversation_id, "assistant", response_text)
                update_conversation_summary(st.session_state.current_conversation_id)
        except Exception:
            st.error("⚠️ Server busy. Please try again.")
    st.rerun()


# USER INPUT
prompt = None

audio_input = st.audio_input("🎤 Bol kar baat karein...")

if audio_input is not None:
    audio_bytes = audio_input.getvalue()
    if "last_processed_audio" not in st.session_state or st.session_state.last_processed_audio != audio_bytes:
        st.session_state.last_processed_audio = audio_bytes
        with st.spinner("🎧 LUCIA sun rahi hai..."):
            recognized_text = transcribe_audio(audio_bytes)
            if recognized_text:
                prompt = recognized_text

text_prompt = st.chat_input("Talk to LUCIA...")
if text_prompt:
    prompt = text_prompt


# PROCESS QUERY
if prompt:
    conv_id = st.session_state.current_conversation_id

    st.session_state.messages.append(HumanMessage(content=prompt))
    save_message(conv_id, "user", prompt)
    with st.chat_message("user"):
        st.write(prompt)

    if len(get_messages(conv_id)) == 1:
        update_conversation_title(conv_id, generate_title_local(prompt))

    try:
        decision = decide_action(prompt, summary_model)
    except Exception:
        decision = {"action": "chat"}
    
    tool_result = None
    is_tool_action = decision.get("action") in ["tool", "tool_sequence"] or "tools" in decision or "tool" in decision
    
    if is_tool_action and decision.get("action") != "chat":
        with st.spinner(f"⚙️ Kaam kar rahi hoon..."):
            tool_result = execute_tool(decision)
        
        # ⚡ Handle clarification requests (missing email fields)
        if tool_result.get("needs_clarification"):
            # Don't show draft card, let LLM ask naturally
            pass
        
        # Save draft to session for Card Rendering (only if complete)
        elif tool_result.get("draft"):
            st.session_state.pending_draft = tool_result["draft"]
            
            # Show auto-fill notification
            auto_info = tool_result.get("auto_filled", {})
            if auto_info.get("signature_added"):
                st.info(f"✍️ Auto-signed as: **{auto_info.get('name', 'User')}**")
        
        if decision.get("tool") == "generate_code_file" and tool_result.get("data"):
            with st.chat_message("assistant"):
                st.code(tool_result["data"], language="python")

    # Build context with tool result injected
    context = build_chat_context(
        conv_id, 
        st.session_state.messages[-6:], 
        tool_result=tool_result, 
        decision=decision
    )

    with st.chat_message("assistant"):
        try:
            raw_res = st.write_stream(stream_response(context))
            response_text = str(raw_res) if raw_res is not None else ""
            
            if response_text.strip():
                if enable_voice_out:
                    with st.spinner("🔊 Generating voice..."):
                        audio_bytes = synthesize_google_tts(response_text)
                        st.session_state.current_audio = audio_bytes

                st.session_state.messages.append(AIMessage(content=response_text))
                save_message(conv_id, "assistant", response_text)
                update_conversation_summary(conv_id)
            
        except Exception as e:
            st.error(f"⚠️ Error: {e}")

    st.rerun()
"""
LUCIA FastAPI Server
High-performance REST & Server-Sent Events (SSE)
bridge between Next.js frontend and LUCIA Core.
"""

import os
import json
import time
import asyncio
from pathlib import Path
from typing import Optional

from fastapi import (
    FastAPI,
    HTTPException,
    UploadFile,
    File,
)

from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, Response
from pydantic import BaseModel
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
# LANGCHAIN
# ============================================================

from langchain_core.messages import (
    HumanMessage,
    AIMessage,
)


# ============================================================
# CORE IMPORTS
# ============================================================

from lucia_core import (
    model,
    summary_model,
    build_chat_context,
    update_conversation_summary,
    generate_title_local,
)


# ============================================================
# DATABASE
# ============================================================

from database import (
    get_all_conversations,
    create_conversation,
    get_messages,
    get_recent_messages,
    delete_conversation,
    save_message,
    get_summary,
    get_global_memories,
    update_conversation_title,
)


# ============================================================
# TOOLS
# ============================================================

from tool_router import (
    decide_action,
    execute_tool,
)


# ============================================================
# AUDIO
# ============================================================

from audio_engine_backup import (
    transcribe_audio,
    synthesize_audio_async,
)


# ============================================================
# LLM GATEWAY
# ============================================================

from llm_gateway import gateway


# ============================================================
# FILE PROCESSING
# ============================================================

from file_processor import (
    process_uploaded_file,
    get_attachment,
    delete_attachment,
    build_attachment_context,
)


# ============================================================
# FASTAPI
# ============================================================

app = FastAPI(
    title="LUCIA Core API",
    version="1.0.0",
)


# ============================================================
# CORS
# ============================================================

app.add_middleware(
    CORSMiddleware,

    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "*",
    ],

    allow_credentials=True,

    allow_methods=["*"],

    allow_headers=["*"],
)


# ============================================================
# REQUEST / RESPONSE SCHEMAS
# ============================================================

class ChatRequest(BaseModel):
    message: str
    conversationId: Optional[str] = None
    attachmentIds: Optional[list[str]] = []


class CreateConversationRequest(BaseModel):
    title: Optional[str] = "New Conversation"


# ============================================================
# CONVERSATION ENDPOINTS
# ============================================================

@app.get("/conversations")
async def list_conversations():

    convs = get_all_conversations()

    return [
        {
            "id": str(c[0]),
            "title": c[1],
            "updatedAt": (
                c[2]
                if len(c) > 2 and c[2]
                else time.strftime(
                    "%Y-%m-%dT%H:%M:%SZ",
                    time.gmtime(),
                )
            ),
        }
        for c in convs
    ]


@app.post("/conversations")
async def new_conversation(
    req: CreateConversationRequest,
):

    title = req.title or "New Conversation"

    conv_id = create_conversation(
        title=title,
    )

    return {
        "id": str(conv_id),
        "title": title,
        "updatedAt": time.strftime(
            "%Y-%m-%dT%H:%M:%SZ",
            time.gmtime(),
        ),
    }


@app.get("/conversations/{conv_id}/messages")
async def get_conversation_messages(
    conv_id: int,
):

    raw_msgs = get_messages(
        conv_id,
    )

    return [
        {
            "id": str(m[0]),
            "role": m[1],
            "content": m[2],
            "timestamp": time.strftime(
                "%Y-%m-%dT%H:%M:%SZ",
                time.gmtime(),
            ),
        }
        for m in raw_msgs
    ]


@app.delete("/conversations/{conv_id}")
async def remove_conversation(
    conv_id: int,
):

    delete_conversation(
        conv_id,
    )

    return {
        "success": True,
        "message": (
            f"Conversation {conv_id} deleted"
        ),
    }


# ============================================================
# AUDIO ENDPOINTS
# ============================================================

@app.post("/audio/transcribe")
async def transcribe_mic_audio(
    file: UploadFile = File(...),
):

    try:

        audio_bytes = await file.read()

        if not audio_bytes:

            raise HTTPException(
                status_code=400,
                detail="Empty audio file",
            )

        transcribed_text = transcribe_audio(
            audio_bytes,
        )

        return {
            "text": transcribed_text,
        }

    except HTTPException:

        raise

    except Exception as e:

        raise HTTPException(
            status_code=500,
            detail=f"Transcription failed: {e}",
        )


@app.get("/audio/synthesize")
async def synthesize_response_voice(
    text: str,
):

    try:

        if not text.strip():

            raise HTTPException(
                status_code=400,
                detail="Empty text",
            )

        audio_bytes = await synthesize_audio_async(
            text,
        )

        if not audio_bytes:

            raise HTTPException(
                status_code=500,
                detail="Voice synthesis failed",
            )

        return Response(
            content=audio_bytes,
            media_type="audio/mpeg",
            headers={
                "Cache-Control": (
                    "public, max-age=3600"
                ),
                "Content-Length": str(
                    len(audio_bytes)
                ),
            },
        )

    except HTTPException:

        raise

    except Exception as e:

        raise HTTPException(
            status_code=500,
            detail=str(e),
        )


# ============================================================
# STATUS ENDPOINTS
# ============================================================

@app.get("/providers/status")
async def providers_status():

    health = gateway.get_health_report()

    return [
        {
            "id": name,

            "name": name.replace(
                "_",
                " ",
            ).title(),

            "status": (
                "healthy"
                if info["status"] == "HEALTHY"
                else (
                    "cooldown"
                    if info["status"] == "COOLDOWN"
                    else "available"
                )
            ),

            "model": (
                "llama-3.3-70b"
                if "groq" in name
                else (
                    "Qwen3.5-9B"
                    if "huggingface" in name
                    else "gemini-2.0-flash"
                )
            ),
        }

        for name, info in health.items()
    ]


@app.get("/system/status")
async def system_status():

    return {
        "online": True,
        "aiGateway": "operational",
        "tools": "operational",
        "gmail": (
            "connected"
            if (
                Path(__file__).resolve().parent
                / "token.json"
            ).exists()
            else "disconnected"
        ),
        "memory": "operational",
    }


# ============================================================
# FILE UPLOAD ENDPOINTS
# ============================================================

@app.post("/api/files/upload")
async def upload_file(
    file: UploadFile = File(...),
):

    try:

        file_bytes = await file.read()

        if not file_bytes:

            raise HTTPException(
                status_code=400,
                detail="Empty file",
            )

        result = process_uploaded_file(
            file_bytes,
            file.filename,
        )

        if not result["success"]:

            raise HTTPException(
                status_code=400,
                detail=result["message"],
            )

        return result["attachment"]

    except HTTPException:

        raise

    except Exception as e:

        raise HTTPException(
            status_code=500,
            detail=f"Upload failed: {e}",
        )


@app.get("/api/files/{file_id}")
async def get_file_info(
    file_id: str,
):

    att = get_attachment(
        file_id,
    )

    if not att:

        raise HTTPException(
            status_code=404,
            detail="Attachment not found",
        )

    return {
        key: value
        for key, value in att.items()
        if key not in [
            "base64Image",
            "storageReference",
        ]
    }


@app.delete("/api/files/{file_id}")
async def remove_file(
    file_id: str,
):

    success = delete_attachment(
        file_id,
    )

    if not success:

        raise HTTPException(
            status_code=404,
            detail="Attachment not found",
        )

    return {
        "success": True,
    }


# ============================================================
# REAL-TIME STREAMING CHAT
# ============================================================

@app.post("/chat/stream")
async def chat_stream(
    req: ChatRequest,
):

    user_prompt = req.message.strip()

    if not user_prompt:

        raise HTTPException(
            status_code=400,
            detail="Message cannot be empty",
        )

    # --------------------------------------------------------
    # CONVERSATION
    # --------------------------------------------------------

    if (
        not req.conversationId
        or req.conversationId == "undefined"
    ):

        conv_id = create_conversation(
            title="New Conversation",
        )

    else:

        try:

            conv_id = int(
                req.conversationId,
            )

        except ValueError:

            conv_id = create_conversation(
                title="New Conversation",
            )

    # --------------------------------------------------------
    # SAVE USER MESSAGE
    # --------------------------------------------------------

    save_message(
        conv_id,
        "user",
        user_prompt,
    )

    # --------------------------------------------------------
    # GENERATE TITLE
    # --------------------------------------------------------

    existing_msgs = get_messages(
        conv_id,
    )

    if len(existing_msgs) <= 1:

        new_title = generate_title_local(
            user_prompt,
        )

        update_conversation_title(
            conv_id,
            new_title,
        )

    # ========================================================
    # SSE GENERATOR
    # ========================================================

    async def event_generator():

        t0 = time.time()

        # ----------------------------------------------------
        # AGENT DECISION
        # ----------------------------------------------------

        try:

            decision = decide_action(
                user_prompt,
                summary_model,
            )

        except Exception as exc:

            print(
                f"[LUCIA] Tool decision failed: {exc}"
            )

            decision = {
                "action": "chat",
            }

        # ----------------------------------------------------
        # TOOL EXECUTION
        # ----------------------------------------------------

        tool_result = None

        is_tool = (
            decision.get("action")
            in [
                "tool",
                "tool_sequence",
            ]
            or "tools" in decision
            or "tool" in decision
        )

        if (
            is_tool
            and decision.get("action")
            != "chat"
        ):

            tool_name = decision.get(
                "tool",
                "tool_sequence",
            )

            yield (
                "data: "
                + json.dumps({
                    "activity": {
                        "active": True,
                        "status": "using-tool",
                        "detail": (
                            f"Using {tool_name}"
                        ),
                    }
                })
                + "\n\n"
            )

            await asyncio.sleep(
                0.05,
            )

            try:

                tool_result = execute_tool(
                    decision,
                )

            except Exception as exc:

                tool_result = (
                    f"Tool execution failed: {exc}"
                )

                print(
                    f"[LUCIA] Tool error: {exc}"
                )

        # ----------------------------------------------------
        # RECENT MESSAGES
        # ----------------------------------------------------

        recent = get_recent_messages(
            conv_id,
            limit=6,
        )

        recent_msgs = []

        for role, content in recent:

            if role == "user":

                recent_msgs.append(
                    HumanMessage(
                        content=content,
                    )
                )

            elif role == "assistant":

                recent_msgs.append(
                    AIMessage(
                        content=content,
                    )
                )

        # ----------------------------------------------------
        # ATTACHMENTS
        # ----------------------------------------------------

        attachment_context = ""

        if req.attachmentIds:

            try:

                attachment_context = (
                    build_attachment_context(
                        req.attachmentIds,
                    )
                )

            except Exception as exc:

                print(
                    "[LUCIA] Attachment context "
                    f"failed: {exc}"
                )

        # ----------------------------------------------------
        # BUILD CONTEXT
        # ----------------------------------------------------

        context = build_chat_context(
            recent_messages=recent_msgs,
            conversation_id=conv_id,
            tool_result=tool_result,
            attachments=(
                req.attachmentIds
                if req.attachmentIds
                else None
            ),
        )

        # ----------------------------------------------------
        # OPTIONAL DECISION CONTEXT
        # ----------------------------------------------------

        if decision and decision.get("action") != "chat":

            decision_text = json.dumps(
                decision,
                ensure_ascii=False,
                separators=(",", ":"),
            )

            from langchain_core.messages import SystemMessage

            context.append(
                SystemMessage(
                    content=(
                        "CURRENT AGENT DECISION:\n"
                        + decision_text[:3000]
                    )
                )
            )

        # ----------------------------------------------------
        # ACTIVITY COMPLETE
        # ----------------------------------------------------

        yield (
            "data: "
            + json.dumps({
                "activity": {
                    "active": False,
                },
                "conversationId": str(
                    conv_id,
                ),
            })
            + "\n\n"
        )

        # ----------------------------------------------------
        # STREAM LLM RESPONSE
        # ----------------------------------------------------

        full_reply = ""

        try:

            for chunk in model.stream(
                context,
            ):

                token = (
                    chunk.content
                    if hasattr(
                        chunk,
                        "content",
                    )
                    else str(chunk)
                )

                if not token:

                    continue

                full_reply += token

                yield (
                    "data: "
                    + json.dumps({
                        "token": token,
                    })
                    + "\n\n"
                )

                await asyncio.sleep(
                    0.002,
                )

        except Exception as e:

            print(
                f"[LUCIA] Streaming error: {e}"
            )

            error_msg = (
                "\n\n"
                "[LUCIA Notice: "
                f"{e}]"
            )

            full_reply += error_msg

            yield (
                "data: "
                + json.dumps({
                    "token": error_msg,
                })
                + "\n\n"
            )

        # ----------------------------------------------------
        # SAVE RESPONSE
        # ----------------------------------------------------

        if full_reply.strip():

            save_message(
                conv_id,
                "assistant",
                full_reply,
            )

        # ----------------------------------------------------
        # SUMMARY — NON-BLOCKING BACKGROUND TASK
        # ----------------------------------------------------

        if full_reply.strip():

            try:

                asyncio.create_task(
                    asyncio.to_thread(
                        update_conversation_summary,
                        conv_id,
                    )
                )

                print(
                    "[LUCIA] Conversation summary scheduled "
                    f"in background for conversation {conv_id}"
                )

            except Exception as exc:

                print(
                    "[LUCIA] Failed to schedule background "
                    f"summary task: {exc}"
                )

        # ----------------------------------------------------
        # METADATA
        # ----------------------------------------------------

        elapsed = (
            time.time()
            - t0
        )

        yield (
            "data: "
            + json.dumps({
                "metadata": {
                    "provider": (
                        "LUCIA Gateway"
                    ),
                    "model": (
                        "Gateway Selected Model"
                    ),
                    "responseTime": elapsed,
                    "tokensIn": (
                        len(user_prompt.split())
                        * 2
                    ),
                    "tokensOut": (
                        len(full_reply.split())
                        * 2
                    ),
                }
            })
            + "\n\n"
        )

        # ----------------------------------------------------
        # END EVENT
        # ----------------------------------------------------

        yield (
            "data: "
            + json.dumps({
                "done": True,
            })
            + "\n\n"
        )

    # ========================================================
    # STREAM RESPONSE
    # ========================================================

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":

    import uvicorn

    print(
        "🚀 Starting LUCIA Core FastAPI Server..."
    )

    uvicorn.run(
        "api_server:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
    )
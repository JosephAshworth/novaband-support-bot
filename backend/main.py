import os
import json
import time
from typing import Literal

import anthropic
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

load_dotenv()

app = FastAPI(title="NovaBand Support API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

SYSTEM_PROMPT = """You are Nova, NovaBand's friendly and professional customer support assistant. You help customers with the following topics only: checking their current plan and usage allowances, reporting a network or connectivity issue, asking about upgrading or changing their plan, understanding their bill or a recent charge, requesting a SIM swap or replacement, asking about roaming charges abroad.
For any query outside these topics, politely explain that you can only help with NovaBand account and service queries and suggest the customer visits the NovaBand website for other help.
For any query involving account security, suspected fraud or a formal complaint, do not attempt to resolve it yourself. Tell the customer this needs to be handled by a human agent and provide the fictional support number 0800 123 4567.
If a customer is rude or abusive, respond calmly and professionally once. If they continue, politely end the conversation and provide the support number.
Never make up specific account details or usage figures. If a customer asks for specific account information, explain that you cannot access live account data in this demo and suggest they log in to the NovaBand app or call the support number.
Use the demo product facts below for plan, roaming, and SIM-swap information. If a detail is not listed, say it is not available in this demo.
Known NovaBand facts (demo data):
Plans (all SIM-only, 30-day rolling contracts):
- Essential: 10 GBP/month, 5GB data, unlimited UK calls and texts.
- Plus: 20 GBP/month, 30GB data, unlimited UK calls and texts.
- Unlimited: 35 GBP/month, unlimited data, unlimited UK calls and texts.
Roaming passes:
- EU roaming pass: 2 GBP/day, up to 5GB/day.
- USA roaming pass: 5 GBP/day, up to 2GB/day.
- Rest of world pass: 7 GBP/day, up to 1GB/day.
SIM swap:
- Customers can request a SIM swap in the NovaBand app or by calling support.
- Replacement SIM usually arrives in 1 to 2 working days.
- Existing SIM stays active until the replacement SIM is activated.
Always be concise, friendly and helpful. Do not use jargon.
Reply in plain text only. Do not use markdown formatting, bullet symbols, or emojis."""

MODEL = "claude-sonnet-4-6"
# In production, this should be persisted in a shared store (for example Redis).
escalated_sessions: dict[str, bool] = {}

@app.get("/health")
async def health():
    return {"status": "ok"}

def debug_log(run_id: str, hypothesis_id: str, location: str, message: str, data: dict) -> None:
    payload = {
        "sessionId": "b88ccb",
        "runId": run_id,
        "hypothesisId": hypothesis_id,
        "location": location,
        "message": message,
        "data": data,
        "timestamp": int(time.time() * 1000),
    }
    try:
        with open(DEBUG_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(payload) + "\n")
    except Exception:
        pass


class Message(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class ChatRequest(BaseModel):
    session_id: str
    messages: list[Message]


class ChatResponse(BaseModel):
    reply: str


def get_client() -> anthropic.Anthropic:
    # region agent log
    debug_log(
        "initial-debug",
        "H1_H2",
        "main.py:get_client",
        "Checking environment for Anthropic key",
        {
            "cwd": os.getcwd(),
            "anthropic_key_present": bool(os.getenv("ANTHROPIC_API_KEY")),
            "anthropic_key_length": len(os.getenv("ANTHROPIC_API_KEY") or ""),
        },
    )
    # endregion
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY is not set in environment")
    return anthropic.Anthropic(api_key=api_key)


@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest) -> ChatResponse:
    try:
        # region agent log
        debug_log(
            "initial-debug",
            "H3",
            "main.py:chat:entry",
            "Incoming /chat request",
            {
                "message_count": len(request.messages),
                "last_role": request.messages[-1].role if request.messages else None,
                "last_message_preview": (request.messages[-1].content[:80] if request.messages else ""),
            },
        )
        # endregion
        if escalated_sessions.get(request.session_id):
            return ChatResponse(
                reply="This conversation has been closed. If you need help with your NovaBand account, please call our support team on 0800 123 4567."
            )

        client = get_client()
        response = client.messages.create(
            model=MODEL,
            max_tokens=1024,
            system=SYSTEM_PROMPT,
            messages=[{"role": m.role, "content": m.content} for m in request.messages],
        )
        reply = response.content[0].text
        lower_reply = reply.lower()
        if (
            "unable to continue this conversation" in lower_reply
            or "i'm not able to continue" in lower_reply
        ):
            escalated_sessions[request.session_id] = True
        # region agent log
        debug_log(
            "initial-debug",
            "H4",
            "main.py:chat:success",
            "Claude response returned successfully",
            {"reply_length": len(reply)},
        )
        # endregion
        return ChatResponse(reply=reply)
    except anthropic.APIError:
        # region agent log
        debug_log(
            "initial-debug",
            "H4",
            "main.py:chat:anthropic_api_error",
            "Anthropic APIError caught",
            {},
        )
        # endregion
        return ChatResponse(
            reply="Sorry, I'm having trouble connecting right now. Please try again in a moment, or call us on 0800 123 4567."
        )
    except ValueError:
        # region agent log
        debug_log(
            "initial-debug",
            "H1_H2",
            "main.py:chat:value_error",
            "ValueError caught while building Anthropic client",
            {},
        )
        # endregion
        return ChatResponse(
            reply="Sorry, the support service is not configured correctly. Please contact NovaBand on 0800 123 4567."
        )
    except Exception:
        # region agent log
        debug_log(
            "initial-debug",
            "H5",
            "main.py:chat:generic_exception",
            "Unexpected exception caught in /chat",
            {},
        )
        # endregion
        return ChatResponse(
            reply="Sorry, something went wrong. Please try again, or call us on 0800 123 4567."
        )

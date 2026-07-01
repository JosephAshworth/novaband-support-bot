import os
import json
import time
import re
from typing import Literal

import anthropic
import httpx
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
abuse_strikes: dict[str, int] = {}
abuse_audit_log: dict[str, list[dict]] = {}

MAX_ABUSE_STRIKES = 3
MAX_AUDIT_EVENTS_PER_SESSION = 100
DEBUG_LOG_PATH = "/Users/Joseph3/novaband support bot/.cursor/debug-b88ccb.log"

SESSION_CLOSED_REPLY = (
    "This conversation has been closed. If you need help with your NovaBand account, "
    "please call our support team on 0800 123 4567. If you think this was a mistake, "
    "please ask for a moderation review when you call."
)

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


def record_moderation_event(session_id: str, event_type: str, content: str, details: dict) -> None:
    event = {
        "timestamp_ms": int(time.time() * 1000),
        "event_type": event_type,
        "content_excerpt": content[:160],
        "details": details,
    }
    entries = abuse_audit_log.setdefault(session_id, [])
    entries.append(event)
    if len(entries) > MAX_AUDIT_EVENTS_PER_SESSION:
        abuse_audit_log[session_id] = entries[-MAX_AUDIT_EVENTS_PER_SESSION:]


def model_assisted_abuse_check(client: anthropic.Anthropic, text: str) -> dict:
    response = client.messages.create(
        model=MODEL,
        max_tokens=80,
        temperature=0,
        messages=[
            {
                "role": "user",
                "content": (
                    "Classify whether this message is abusive, insulting, or aggressive.\n"
                    "Treat abbreviated profanity, slang, and obfuscated profanity as abusive if likely.\n"
                    "If uncertain, prefer ABUSIVE: yes for safety.\n"
                    "Return exactly three lines and nothing else:\n"
                    "ABUSIVE: yes/no\n"
                    "SEVERITY: low/medium/high\n"
                    "REASON: <short reason>\n\n"
                    f"Message: {text}"
                ),
            }
        ],
    )
    raw = response.content[0].text.strip()
    lower_raw = raw.lower()

    abusive_match = re.search(r"abusive:\s*(yes|true|1|y|no|false|0|n)\b", lower_raw)
    abusive = abusive_match.group(1) in {"yes", "true", "1", "y"} if abusive_match else False
    severity = "unknown"
    for candidate in ("low", "medium", "high"):
        if f"severity: {candidate}" in lower_raw:
            severity = candidate
            break
    # region agent log
    debug_log(
        "initial-debug",
        "H1",
        "main.py:model_assisted_abuse_check",
        "Parsed moderation classifier output",
        {
            "abusive_parsed": abusive,
            "severity_parsed": severity,
            "raw_excerpt": raw[:200],
        },
    )
    # endregion
    return {"abusive": abusive, "severity": severity, "raw": raw}


def evaluate_abuse(client: anthropic.Anthropic, text: str) -> dict:
    try:
        model_result = model_assisted_abuse_check(client, text)
    except Exception:
        # region agent log
        debug_log(
            "initial-debug",
            "H2",
            "main.py:evaluate_abuse",
            "Moderation classifier call failed, using fallback non-abusive result",
            {"text_excerpt": text[:120]},
        )
        # endregion
        model_result = {"abusive": False, "severity": "unknown", "raw": "failed"}

    abusive = model_result["abusive"]
    confidence = "high" if model_result["abusive"] else "low"
    return {
        "abusive": abusive,
        "confidence": confidence,
        "model_result": model_result,
    }


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
    # Avoid inheriting proxy settings from host environment that can break TLS.
    return anthropic.Anthropic(
        api_key=api_key,
        http_client=httpx.Client(trust_env=False, timeout=30.0),
    )


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
            # region agent log
            debug_log(
                "initial-debug",
                "H5",
                "main.py:chat:escalated_short_circuit",
                "Session already escalated; returning closed reply",
                {"session_id": request.session_id},
            )
            # endregion
            return ChatResponse(reply=SESSION_CLOSED_REPLY)

        latest_user_message = ""
        if request.messages and request.messages[-1].role == "user":
            latest_user_message = request.messages[-1].content

        # region agent log
        debug_log(
            "initial-debug",
            "H3_H4_H5",
            "main.py:chat:moderation_precheck",
            "Pre-moderation session state",
            {
                "session_id": request.session_id,
                "latest_role": request.messages[-1].role if request.messages else None,
                "latest_user_message_excerpt": latest_user_message[:120],
                "existing_strikes": abuse_strikes.get(request.session_id, 0),
                "is_escalated": escalated_sessions.get(request.session_id, False),
            },
        )
        # endregion

        client = get_client()
        if latest_user_message:
            abuse_eval = evaluate_abuse(client, latest_user_message)
            # region agent log
            debug_log(
                "initial-debug",
                "H1_H2",
                "main.py:chat:moderation_result",
                "Moderation evaluation completed",
                {
                    "session_id": request.session_id,
                    "abusive": abuse_eval["abusive"],
                    "confidence": abuse_eval["confidence"],
                    "model_severity": abuse_eval["model_result"]["severity"],
                    "model_raw_excerpt": str(abuse_eval["model_result"]["raw"])[:200],
                },
            )
            # endregion
            if abuse_eval["abusive"]:
                current_strikes = abuse_strikes.get(request.session_id, 0) + 1
                abuse_strikes[request.session_id] = current_strikes
                # region agent log
                debug_log(
                    "initial-debug",
                    "H4_H5",
                    "main.py:chat:strike_incremented",
                    "Abusive message detected; incremented strike count",
                    {
                        "session_id": request.session_id,
                        "strike_count": current_strikes,
                        "max_strikes": MAX_ABUSE_STRIKES,
                    },
                )
                # endregion
                record_moderation_event(
                    request.session_id,
                    "abusive_message",
                    latest_user_message,
                    {
                        "strike_count": current_strikes,
                        "max_strikes": MAX_ABUSE_STRIKES,
                        "confidence": abuse_eval["confidence"],
                        "model_severity": abuse_eval["model_result"]["severity"],
                    },
                )

                if current_strikes >= MAX_ABUSE_STRIKES:
                    escalated_sessions[request.session_id] = True
                    # region agent log
                    debug_log(
                        "initial-debug",
                        "H5",
                        "main.py:chat:session_escalated",
                        "Session escalated at strike threshold",
                        {"session_id": request.session_id, "strike_count": current_strikes},
                    )
                    # endregion
                    record_moderation_event(
                        request.session_id,
                        "session_escalated",
                        latest_user_message,
                        {"reason": "max_abuse_strikes_reached"},
                    )
                    return ChatResponse(reply=SESSION_CLOSED_REPLY)

                return ChatResponse(
                    reply=(
                        "I want to help, but I can't continue if abusive language is used. "
                        f"This is warning {current_strikes} of {MAX_ABUSE_STRIKES}. "
                        "If it happens again, I may need to end this conversation and ask you "
                        "to call 0800 123 4567."
                    )
                )
            # region agent log
            debug_log(
                "initial-debug",
                "H1_H2",
                "main.py:chat:not_abusive",
                "Latest message classified as non-abusive; continuing to support flow",
                {"session_id": request.session_id},
            )
            # endregion
        response = client.messages.create(
            model=MODEL,
            max_tokens=1024,
            system=SYSTEM_PROMPT,
            messages=[{"role": m.role, "content": m.content} for m in request.messages],
        )
        reply = response.content[0].text
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

# NovaBand Customer Support Assistant

A conversational AI customer support assistant for **NovaBand**, a fictional UK mobile network operator. Nova helps customers with plan queries, network issues, billing questions, SIM swaps, roaming, and more.

## What This Bot Does

Nova is a demo support assistant for UK mobile customers. It uses the full conversation history plus a guided system prompt to provide consistent, context-aware responses for NovaBand service queries.

## Features

- Multi-turn chat with memory (full message history sent on every request)
- Topic-scoped support for plans, usage, billing, roaming, SIM swaps, and network issues
- Safety/escalation handling for fraud, account security concerns, and formal complaints
- Polite out-of-scope redirects for non-NovaBand questions
- FastAPI backend with a single `/chat` endpoint and React + Tailwind frontend
- Session-based escalation lock for abusive conversations after 2 violations (PostgreSQL-backed persistence)
- Model-driven moderation (no hardcoded profanity list) with structured abuse classification

## Tech Stack

- **Backend:** Python, FastAPI, Anthropic Claude API or Azure OpenAI API
- **Frontend:** React, Vite, Tailwind CSS

## Prerequisites

- Python 3.10+
- Node.js 18+
- PostgreSQL (local instance for development)
- An Anthropic API key (default provider) or Azure OpenAI credentials

Get your Anthropic key from [https://console.anthropic.com/settings/keys](https://console.anthropic.com/settings/keys), or configure Azure OpenAI credentials and deployment details.

## Setup

### 1. Backend

```bash
cd backend
python -m venv venv
source venv/bin/activate   # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

Create a `.env` file in the `backend` directory:

```
ANTHROPIC_API_KEY=your_api_key_here
LLM_PROVIDER=anthropic
AZURE_OPENAI_API_KEY=your_azure_api_key_here
AZURE_OPENAI_ENDPOINT=https://your-resource-name.openai.azure.com
AZURE_OPENAI_DEPLOYMENT_NAME=your_deployment_name
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/novaband_support
```

`LLM_PROVIDER` accepts `anthropic` (default) or `azure_openai`. If unset, the backend uses Anthropic as before.

Create a local PostgreSQL database for the backend session store, for example:

```bash
createdb novaband_support
```

Start the backend:

```bash
uvicorn main:app --reload
```

The API runs at `http://localhost:8000`.

### 2. Frontend

```bash
cd frontend
npm install
npm run dev
```

The chat UI runs at `http://localhost:5173`. Vite proxies `/chat` requests to the backend.

## API

**POST `/chat`**

Request body:

```json
{
  "messages": [
    { "role": "user", "content": "Hello" },
    { "role": "assistant", "content": "Hi, how can I help?" }
  ]
}
```

Response:

```json
{
  "reply": "Assistant response here"
}
```

The frontend sends the full conversation history on every message so the assistant retains context across turns.

## Notes

- The API key must be set in `backend/.env` — it is never hardcoded.
- This is a demo: Nova cannot access live account data and will say so when asked for specific account details.

"""Local test bench for the Cartwheel support agent.

A small web page for running HW1 conversations and reading what the agent
did: every tool call with its arguments and full result, rendered as JSON.
It builds the agent exactly like `agent/cli.py` does (same prompt, tools,
model, auth lookup, and turn cap), so the agent behaves the same; only the
way you view a conversation changes.

It does not judge conversations or write `hw1-session.jsonl`. It shows the
observed fields of a record so they can be copied exactly; the judgment
fields are written by hand.

Run from the repository root:

    uv run python console/server.py

then open http://127.0.0.1:8000
"""

from __future__ import annotations

import json
import subprocess
import sys
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

import uvicorn  # noqa: E402
from agents import RunConfig, Runner, SQLiteSession  # noqa: E402
from agents.items import ItemHelpers, RunItem  # noqa: E402
from fastapi import FastAPI, HTTPException  # noqa: E402
from fastapi.responses import FileResponse  # noqa: E402
from pydantic import BaseModel  # noqa: E402

from agent import db  # noqa: E402
from agent.agent import DEFAULT_MODEL, build_agent, prompt_version  # noqa: E402
from agent.auth import AuthContext  # noqa: E402
from agent.cli import MAX_TURNS  # noqa: E402
from observability.instrument import load_env  # noqa: E402

load_env()

PAGE = Path(__file__).with_name("index.html")
app = FastAPI(title="Cartwheel test bench")


@dataclass
class Conversation:
    ctx: AuthContext
    user_name: str
    agent: Any
    session: SQLiteSession
    turns: list[dict[str, Any]] = field(default_factory=list)


_CONVERSATIONS: dict[str, Conversation] = {}


class ConversationCreate(BaseModel):
    role: str
    user_id: int


class MessageCreate(BaseModel):
    text: str


def _as_json_value(value: Any) -> Any:
    """Tool outputs usually arrive as dicts; decode strings that hold JSON."""
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value
    return value


def _tool_calls(new_items: list[RunItem]) -> list[dict[str, Any]]:
    """Pair each tool call with its output, in call order (as the CLI's --debug does)."""
    outputs = {
        item.call_id: item.output
        for item in new_items
        if item.type == "tool_call_output_item" and item.call_id is not None
    }
    calls = []
    for item in new_items:
        if item.type != "tool_call_item":
            continue
        raw = item.raw_item
        args = raw.get("arguments") if isinstance(raw, dict) else getattr(raw, "arguments", None)
        calls.append(
            {
                "name": item.tool_name,
                "arguments": _as_json_value(args),
                "result": _as_json_value(outputs.get(item.call_id)),
            }
        )
    return calls


def _steps(new_items: list[RunItem], final_output: Any) -> list[dict[str, Any]]:
    """Everything the agent produced, in order: in-between messages and tool calls.

    The final answer is left out (it is shown as the response). The handout's
    record has no field for in-between messages, so they are display-only.
    """
    calls = iter(_tool_calls(new_items))
    messages = [item for item in new_items if item.type == "message_output_item"]
    final = messages[-1] if messages and ItemHelpers.text_message_output(messages[-1]) == final_output else None
    steps = []
    for item in new_items:
        if item.type == "tool_call_item":
            steps.append({"type": "tool_call", **next(calls)})
        elif item.type == "message_output_item" and item is not final:
            text = ItemHelpers.text_message_output(item).strip()
            if text:
                steps.append({"type": "note", "text": text})
    return steps


@app.get("/")
def page() -> FileResponse:
    return FileResponse(PAGE)


@app.get("/api/config")
def config() -> dict[str, Any]:
    import os

    return {
        "model": os.environ.get("CARTWHEEL_MODEL") or DEFAULT_MODEL,
        "prompt_version": prompt_version(),
    }


@app.post("/api/conversations")
def create_conversation(body: ConversationCreate) -> dict[str, Any]:
    with db.connection() as conn:
        user = db.get_user(conn, body.user_id)
    if user is None:
        raise HTTPException(404, f"No user with id {body.user_id}.")
    if user.role != body.role:
        raise HTTPException(
            400, f"User {user.id} is a {user.role}, not a {body.role}. Pick a matching user."
        )
    ctx = AuthContext(user_id=user.id, role=user.role, store_id=user.store_id)
    conversation_id = uuid.uuid4().hex[:12]
    _CONVERSATIONS[conversation_id] = Conversation(
        ctx=ctx,
        user_name=user.name,
        agent=build_agent(ctx),
        session=SQLiteSession(f"console-{conversation_id}"),
    )
    return {
        "conversation_id": conversation_id,
        "role": ctx.role,
        "user_id": ctx.user_id,
        "store_id": ctx.store_id,
        "user_name": user.name,
    }


@app.post("/api/conversations/{conversation_id}/messages")
async def send_message(conversation_id: str, body: MessageCreate) -> dict[str, Any]:
    conversation = _CONVERSATIONS.get(conversation_id)
    if conversation is None:
        raise HTTPException(404, "This conversation has ended. Start a new conversation.")
    text = body.text.strip()
    if not text:
        raise HTTPException(400, "Type a message first.")
    try:
        result = await Runner.run(
            conversation.agent,
            text,
            session=conversation.session,
            context=conversation.ctx,
            max_turns=MAX_TURNS,
            run_config=RunConfig(tracing_disabled=True),
        )
    except Exception as exc:  # surface model/key errors in the page instead of a 500 page
        raise HTTPException(502, f"The agent run failed: {exc}") from exc
    turn = {
        "request": text,
        "tool_calls": _tool_calls(result.new_items),
        "response": result.final_output,
        "steps": _steps(result.new_items, result.final_output),
    }
    conversation.turns.append(turn)
    return turn


@app.post("/api/reset-data")
def reset_data() -> dict[str, Any]:
    run = subprocess.run(
        [sys.executable, "-m", "seed.generate"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    if run.returncode != 0:
        raise HTTPException(500, f"Reset failed: {run.stderr.strip()[-500:]}")
    _CONVERSATIONS.clear()
    return {"ok": True, "output": run.stdout.strip()}


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)

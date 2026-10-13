# Cartwheel test bench

A small local web page for running Homework 1 conversations with the Cartwheel support agent and reading exactly what the agent did.

I built it because the CLI's `--debug` output is hard to read and prints tool results in Python format (`True`, `None`, single quotes), so copying them into `hw1-session.jsonl` by hand is slow and error-prone.

## What it does

- Starts each conversation as a chosen role and user (shopper 1, merchant 9002, support 9501, or any user ID), with no memory of earlier conversations.
- Sends one message per conversation by default. A follow-up is available for cases where the agent asks something it needs before acting.
- Shows every tool call in order, with the exact arguments the model chose and the full result, rendered as JSON with an ok, error, or queued-for-approval marker.
- Shows the six observed fields of a session record (`role`, `user_id`, `store_id`, `request`, `tool_calls`, `response`) as one JSON line with a copy button.
- Resets the local database (`python -m seed.generate`) after a test refund or cancellation, with a confirmation step.

## What it does not do

- It does not judge conversations or write `hw1-session.jsonl`. The judgment fields (`expected`, `requirement`, `met_requirement`, `problem_source`) are written by hand.
- It does not change agent behavior. It builds the agent the same way `agent/cli.py` does: same system prompt, tools, model from `.env`, auth lookup from the users table, and turn cap.

## Run it

From the repository root:

```bash
uv run python console/server.py
```

Then open http://127.0.0.1:8000. It uses only packages already in the project (FastAPI and Uvicorn) and listens on your own machine only.

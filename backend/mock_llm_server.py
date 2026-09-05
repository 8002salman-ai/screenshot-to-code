"""Mock OpenAI Responses API for deterministic end-to-end pipeline testing.

Emulates the subset of the Responses SSE protocol that
backend/agent/providers/openai.py consumes:

  response.created
  response.output_item.added        (type=function_call, with call_id)
  response.output_text.delta        (assistant text chunks)
  response.function_call_arguments.delta / .done
  response.output_item.done
  response.completed                (carries usage)

Scripted conversation:
  turn 1 -> tool call create_file(path, content)  [full HTML in one delta]
  turn 2 -> plain assistant text (no tool calls) -> engine finalizes

Run:  poetry run uvicorn mock_llm_server:app --port 9101
"""

import json
import uuid
from typing import Any, AsyncIterator, Dict, List

from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse

MOCK_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>MockNotes Pricing</title>
  <script src="https://cdn.tailwindcss.com"></script>
</head>
<body class="bg-slate-900 text-slate-100 min-h-screen flex items-center justify-center">
  <div class="max-w-4xl mx-auto p-8">
    <h1 class="text-4xl font-bold mb-2 text-center">MockNotes</h1>
    <p class="text-slate-400 text-center mb-8">Simple pricing for every team</p>
    <div class="grid grid-cols-3 gap-6">
      <div class="bg-slate-800 rounded-xl p-6">
        <h2 class="text-xl font-semibold mb-2">Free</h2>
        <p class="text-3xl font-bold mb-4">$0<span class="text-sm text-slate-400">/mo</span></p>
        <ul class="text-slate-300 space-y-1 mb-6"><li>3 projects</li><li>Community support</li></ul>
        <button class="w-full bg-slate-700 py-2 rounded-lg">Get started</button>
      </div>
      <div class="bg-indigo-600 rounded-xl p-6 scale-105">
        <h2 class="text-xl font-semibold mb-2">Pro</h2>
        <p class="text-3xl font-bold mb-4">$12<span class="text-sm text-indigo-200">/mo</span></p>
        <ul class="text-indigo-100 space-y-1 mb-6"><li>Unlimited projects</li><li>Priority support</li></ul>
        <button class="w-full bg-white text-indigo-700 py-2 rounded-lg">Choose Pro</button>
      </div>
      <div class="bg-slate-800 rounded-xl p-6">
        <h2 class="text-xl font-semibold mb-2">Team</h2>
        <p class="text-3xl font-bold mb-4">$29<span class="text-sm text-slate-400">/mo</span></p>
        <ul class="text-slate-300 space-y-1 mb-6"><li>Everything in Pro</li><li>SSO &amp; admin</li></ul>
        <button class="w-full bg-slate-700 py-2 rounded-lg">Contact sales</button>
      </div>
    </div>
  </div>
</body>
</html>
"""

app = FastAPI()


def sse_event(payload: Dict[str, Any]) -> str:
    return f"event: {payload.get('type')}\ndata: {json.dumps(payload)}\n\n"


def response_envelope(response_id: str) -> Dict[str, Any]:
    # Full Response-object shape; the openai SDK pydantic models expect
    # these fields on response.created / response.completed events.
    return {
        "id": response_id,
        "object": "response",
        "created_at": 1700000000,
        "status": "completed",
        "model": "gpt-5.4-mini",
        "output": [],
        "parallel_tool_calls": True,
        "tool_choice": "auto",
        "tools": [],
        "error": None,
        "incomplete_details": None,
        "instructions": None,
        "metadata": {},
        "temperature": 1.0,
        "top_p": 1.0,
        "previous_response_id": None,
        "reasoning": {"effort": None, "summary": None},
        "store": False,
        "text": {"format": {"type": "text"}},
        "truncation": "disabled",
        "usage": None,
        "user": None,
    }


@app.post("/v1/responses")
async def responses(request: Request) -> StreamingResponse:
    body = await request.json()
    input_items: List[Dict[str, Any]] = body.get("input", [])

    # Turn 2 happens when function_call_output items appear in the input.
    has_tool_output = any(
        item.get("type") == "function_call_output" for item in input_items
    )

    response_id = f"resp_mock_{uuid.uuid4().hex[:12]}"

    async def event_stream() -> AsyncIterator[str]:
        yield sse_event(
            {"type": "response.created", "response": response_envelope(response_id)}
        )

        if not has_tool_output:
            # ---- Turn 1: emit a create_file tool call --------------
            call_id = f"call_mock_{uuid.uuid4().hex[:10]}"
            args = json.dumps(
                {"path": "index.html", "content": MOCK_HTML}
            )

            item = {
                "type": "function_call",
                "id": f"fc_{uuid.uuid4().hex[:8]}",
                "call_id": call_id,
                "name": "create_file",
                "arguments": "",
            }
            yield sse_event(
                {
                    "type": "response.output_item.added",
                    "output_index": 0,
                    "item": item,
                }
            )
            # Stream the arguments in two chunks so the parser exercises
            # both the delta and done paths.
            half = len(args) // 2
            for chunk in (args[:half], args[half:]):
                yield sse_event(
                    {
                        "type": "response.function_call_arguments.delta",
                        "item_id": item["id"],
                        "call_id": call_id,
                        "name": "create_file",
                        "delta": chunk,
                    }
                )
            yield sse_event(
                {
                    "type": "response.function_call_arguments.done",
                    "item_id": item["id"],
                    "call_id": call_id,
                    "name": "create_file",
                    "arguments": args,
                }
            )
            done_item = {**item, "arguments": args}
            yield sse_event(
                {
                    "type": "response.output_item.done",
                    "output_index": 0,
                    "item": done_item,
                }
            )
        else:
            # ---- Turn 2: plain assistant text, no tool calls -------
            text = (
                "Done! I created a dark-theme pricing page with three plans: "
                "Free, Pro $12/mo, and Team $29/mo. The Pro plan is "
                "highlighted. You can ask me to tweak anything."
            )
            for i in range(0, len(text), 40):
                yield sse_event(
                    {
                        "type": "response.output_text.delta",
                        "delta": text[i : i + 40],
                    }
                )

        final = response_envelope(response_id)
        final["usage"] = {
            "input_tokens": 500,
            "output_tokens": 1500,
            "total_tokens": 2000,
            "input_tokens_details": {"cached_tokens": 0},
            "output_tokens_details": {"reasoning_tokens": 0},
        }
        yield sse_event(
            {"type": "response.completed", "response": final}
        )

    return StreamingResponse(
        event_stream(), media_type="text/event-stream"
    )


@app.get("/v1/models")
async def models() -> Dict[str, Any]:
    return {"data": [], "object": "list"}

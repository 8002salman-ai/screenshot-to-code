"""Verify mock-driven generation returns the exact scripted HTML."""
import asyncio
import json
import os
import sys

import websockets

WS_URL = os.environ.get("S2C_MOCK_WS_URL", "ws://127.0.0.1:7003/generate-code")
ATTEMPTS = int(os.environ.get("S2C_MOCK_ATTEMPTS", "3"))


def ws_url() -> str:
    return WS_URL if WS_URL.endswith("/generate-code") else f"{WS_URL}/generate-code"


async def run_once() -> tuple[bool, str]:
    params = {
        "generatedCodeConfig": "html_tailwind",
        "inputMode": "text",
        "generationType": "create",
        "prompt": {"text": "pricing page", "images": [], "videos": []},
        "history": [],
        "fileState": None,
        "optionCodes": [],
        "isImageGenerationEnabled": True,
        "openAiApiKey": "mock-key-for-testing",
        "openAiBaseURL": "http://127.0.0.1:9101/v1",
        "anthropicApiKey": None,
        "geminiApiKey": None,
        "replicateApiKey": None,
    }
    async with websockets.connect(ws_url(), max_size=32 * 1024 * 1024) as ws:
        await ws.send(json.dumps(params))
        code = ""
        while True:
            msg = json.loads(await ws.recv())
            if msg.get("type") == "setCode":
                code = msg.get("value") or ""
            if msg.get("type") == "variantComplete":
                break
    ok = (
        "MockNotes Pricing" in code
        and "$12" in code
        and "$29" in code
        and "Pro" in code
        and "Team" in code
    )
    return ok, code


async def main() -> int:
    last_code = ""
    for attempt in range(1, ATTEMPTS + 1):
        try:
            ok, last_code = await run_once()
        except Exception as exc:  # connection refused while backend warms up
            print(f"attempt {attempt}/{ATTEMPTS}: error {type(exc).__name__}: {exc}")
            ok = False
            await asyncio.sleep(5)
            continue
        if ok:
            print(f"attempt {attempt}/{ATTEMPTS}: PASS")
            print("title ok: True")
            print("len:", len(last_code))
            return 0
        print(f"attempt {attempt}/{ATTEMPTS}: content mismatch")
        await asyncio.sleep(5)
    print("title ok: False")
    print("len:", len(last_code))
    return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

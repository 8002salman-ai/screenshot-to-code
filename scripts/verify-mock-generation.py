"""Verify mock-driven generation returns the exact scripted HTML."""
import asyncio
import json

import websockets


async def main() -> None:
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
    async with websockets.connect(
        "ws://127.0.0.1:7003/generate-code", max_size=32 * 1024 * 1024
    ) as ws:
        await ws.send(json.dumps(params))
        code = ""
        while True:
            msg = json.loads(await ws.recv())
            if msg.get("type") == "setCode":
                code = msg.get("value") or ""
            if msg.get("type") == "variantComplete":
                break
    print("title ok:", "MockNotes Pricing" in code)
    print("Pro $12 ok:", "$12" in code and "Pro" in code)
    print("Team $29 ok:", "$29" in code and "Team" in code)
    print("len:", len(code))


asyncio.run(main())

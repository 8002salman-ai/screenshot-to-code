#!/usr/bin/env python3
"""End-to-end WebSocket test client for screenshot-to-code backend.

Usage: python scripts/test-generation-ws.py [BASE_URL]
  BASE_URL default: ws://127.0.0.1:7001  (local backend)
  For a permanent tunnel: wss://s2c.<your-domain>
"""
import asyncio
import json
import os
import sys
import base64
import urllib.request

BASE = sys.argv[1] if len(sys.argv) > 1 else "ws://127.0.0.1:7001"
URL = f"{BASE}/generate-code"
# Optional per-request key (same channel as the app's Settings dialog).
GEMINI_KEY = os.environ.get("GEMINI_KEY") or None


def fetch_test_image_b64() -> str:
    """Fetch a small public PNG and return base64 data URL."""
    req = urllib.request.Request(
        "https://raw.githubusercontent.com/abi/screenshot-to-code/main/backend/evals/input/nytimes_com.png",
        headers={"User-Agent": "s2c-e2e-test"},
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        data = base64.b64encode(r.read()).decode()
    return f"data:image/png;base64,{data}"


async def run(prompt_payload: dict, label: str, timeout: float = 240) -> int:
    import websockets

    print(f"\n=== {label} ===")
    print(f"Connecting: {URL}")
    messages = []
    code_chunks = {}
    variant_done = set()
    error = None
    close_code = None
    try:
        async with websockets.connect(URL, open_timeout=30, max_size=32 * 1024 * 1024) as ws:
            await ws.send(json.dumps(prompt_payload))
            print("Params sent. Waiting for stream...")
            while True:
                try:
                    raw = await asyncio.wait_for(ws.recv(), timeout=timeout)
                except asyncio.TimeoutError:
                    print(f"[TIMEOUT] No message for {timeout}s")
                    break
                msg = json.loads(raw)
                t = msg.get("type")
                vi = msg.get("variantIndex", 0)
                if t == "chunk":
                    code_chunks.setdefault(vi, "")
                    code_chunks[vi] += msg.get("value") or ""
                elif t == "setCode":
                    # Final code delivered as one message (agent runner path)
                    code_chunks.setdefault(vi, "")
                    code_chunks[vi] += msg.get("value") or ""
                elif t == "variantCount":
                    print(f"  variantCount = {msg.get('value')}")
                elif t == "status":
                    print(f"  [v{vi}] status: {msg.get('value')}")
                elif t == "variantError":
                    print(f"  [v{vi}] variantError: {(msg.get('value') or '')[:200]}")
                elif t == "variantComplete":
                    variant_done.add(vi)
                    size = len(code_chunks.get(vi, ""))
                    print(f"  [v{vi}] COMPLETE ({size} chars)")
                elif t == "error":
                    error = msg.get("value")
                    print(f"  ERROR: {error}")
                elif t in ("thinking", "assistant"):
                    pass
                elif t == "toolStart":
                    pass
                elif t == "toolResult":
                    pass
    except Exception as e:
        # websockets raises ConnectionClosed with code after server closes
        print(f"  [connection ended: {type(e).__name__}: {e}]")
        code_attr = getattr(e, "rcvd", None)
        if code_attr and hasattr(code_attr, "code"):
            close_code = code_attr.code
        elif "code" in str(e):
            pass

    print("\n--- RESULT ---")
    for vi, code in sorted(code_chunks.items()):
        head = " ".join(code[:90].split())
        print(f"variant {vi}: {len(code)} chars | starts: {head[:90]}")
        if code and "--save" in sys.argv:
            out = f"/tmp/s2c-variant-{vi}.html"
            with open(out, "w", encoding="utf-8") as f:
                f.write(code)
            print(f"  saved -> {out}")
    print(f"variants complete: {sorted(variant_done)}")
    print(f"error: {error}")
    print(f"close code: {close_code}")
    ok = bool(code_chunks) and not error
    print(f"VERDICT: {'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


def main() -> None:
    image_b64 = None
    if "--image" in sys.argv:
        print("Fetching test screenshot...")
        image_b64 = fetch_test_image_b64()
        print(f"Image: {len(image_b64) // 1024} KB base64")

    base_params = {
        "generatedCodeConfig": "html_tailwind",
        "codeGenerationModel": "gemini-3-flash-preview-minimal",
        "isImageGenerationEnabled": True,
        "inputMode": "image" if image_b64 else "text",
        "imageGenerationModel": "z_image_turbo",
        "openAiApiKey": None,
        "anthropicApiKey": None,
        "geminiApiKey": GEMINI_KEY,
        "openAiBaseURL": None,
        "replicateApiKey": None,
        "generationType": "create",
        "isTermOfServiceAccepted": True,
        "accessCode": None,
        "prompt": (
            {"text": "", "images": [image_b64], "videos": []}
            if image_b64
            else {
                "text": "A simple landing page for a coffee shop called Bean There "
                "with a hero section, title, subtitle, and a Get Started button",
                "images": [],
                "videos": [],
            }
        ),
        "history": [],
        "fileState": None,
        "optionCodes": [],
    }

    label = "TEXT-MODE generation (no screenshot)" if not image_b64 else "IMAGE-MODE generation (real screenshot)"
    exit_code = asyncio.get_event_loop().run_until_complete(run(base_params, label))
    sys.exit(exit_code)


if __name__ == "__main__":
    main()

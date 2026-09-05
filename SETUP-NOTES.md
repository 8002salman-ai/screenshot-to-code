# Screenshot-to-Code — Local + Cloud Setup Notes

## One-command startup (all services)
`scripts/start-s2c.ps1` (auto-runs at Windows login via the Startup folder):
1. FastAPI backend on :7001 (skips if already running)
2. Vite frontend on :5173 (skips if already running)
3. Cloudflare named tunnel `s2c-backend` (skips if already running; falls back
   to a quick tunnel if the named tunnel is unreachable)
4. Waits for the tunnel, then checks the deployed Vercel bundle: if the backend
   URL it was built with no longer matches the live tunnel URL, it re-pushes
   `VITE_HTTP_BACKEND_URL`/`VITE_WS_BACKEND_URL` (all env targets) and redeploys
   production automatically.

Manual runs:
```powershell
powershell -ExecutionPolicy Bypass -File scripts\start-s2c.ps1            # normal start
powershell -ExecutionPolicy Bypass -File scripts\start-s2c.ps1 -ForceSync # also re-push Vercel env + redeploy
```
Check health/history: `logs\status.log` (per-service logs in `logs\`).
`scripts\check-syntax.ps1` validates the script after edits.

## Run locally (manual, for development)
```bash
# Backend (from repo root)
cd backend && poetry run uvicorn main:app --reload --port 7001

# Frontend (second terminal)
cd frontend && pnpm dev        # open http://localhost:5173
```

## Backend is exposed permanently (named tunnel)
- Tunnel: `s2c-backend` (id 4611daf9-a6b0-4785-b4ce-bdc474f90488)
- URL: `https://s2c.luxedge.us` -> 127.0.0.1:7001 (CNAME in Cloudflare DNS)
- Config: `C:\Users\basco\.cloudflared\s2c-backend.yml`
- Auto-starts on login via `%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\s2c-startup.bat`
- Manual start: `powershell -File scripts\start-s2c.ps1` (starts backend + tunnel + health check)
- Logs: `logs\backend.log`, `logs\cloudflared.log`, `logs\status.log`

Ad-hoc quick tunnel (temporary URL, for testing only):
```bash
cloudflared tunnel --url http://127.0.0.1:7001 --config s2c-cloudflared-ingress.yml --protocol http2
```

## Gotcha found in this setup
`~/.cloudflared/config.yml` contained a stale named tunnel with a catch-all
`http_status:404` rule. That file silently overrides the `--url` flag, making
every quick tunnel return 404. The `--config s2c-cloudflared-ingress.yml` flag
in this repo overrides it back. Either keep passing `--config`, or fix/delete
`~/.cloudflared/config.yml`.

## Deployed
- Frontend (Vercel): https://frontend-kohl-gamma-12.vercel.app
- Backend: https://s2c.luxedge.us (permanent Cloudflare tunnel, WebSockets verified)

## Git repo + automatic deploys
- Repo: https://github.com/8002salman-ai/screenshot-to-code (private, main branch)
- `origin` = your repo, `upstream` = abi/screenshot-to-code (pull updates with
  `git pull upstream main`)
- Vercel project `frontend` is connected to the repo: every push to `main`
  auto-deploys production; PRs get preview deployments.
- Root `vercel.json` makes the monorepo build work (builds `frontend/`, pins
  pnpm 10.32.1 via npx to avoid the ERR_INVALID_THIS registry bug).
- Env vars (`VITE_HTTP_BACKEND_URL`, `VITE_WS_BACKEND_URL`) live in the Vercel
  project and are injected at build time; scripts/start-s2c.ps1 re-pushes them
  and redeploys if the tunnel URL ever changes.

## API keys
Backend needs at least one LLM key in `backend/.env`:
`OPENAI_API_KEY` / `ANTHROPIC_API_KEY` / `GEMINI_API_KEY`
(+ `REPLICATE_API_KEY` for image tools). Restart the backend after editing.

**Current: GEMINI_API_KEY is set** (free tier). Notes:
- Free tier = 20 requests/min per model. Keep `NUM_VARIANTS=1` (set in
  `backend/.env`) or generation hits 429s.
- `gemini-3.5-flash` is the lead create model (its own quota pool).
- Keys can also be pasted per-session in the app Settings dialog
  (sent per-request, stored in browser localStorage).

## Mock-LLM pipeline test (no API key needed)
`backend/mock_llm_server.py` emulates the OpenAI Responses API (SSE) and
scripts a two-turn agent conversation (create_file tool call -> final text).

```bash
# 1) mock LLM on :9101
cd backend && poetry run uvicorn mock_llm_server:app --port 9101

# 2) backend on :7003 pointed at the mock (forces OPENAI_ONLY model set)
cd backend
OPENAI_BASE_URL=http://127.0.0.1:9101/v1 OPENAI_API_KEY=mock-key-for-testing \
GEMINI_API_KEY= ANTHROPIC_API_KEY= NUM_VARIANTS=1 \
poetry run uvicorn main:app --port 7003

# 3) headless verification (exact scripted HTML round-trips)
poetry run python ../scripts/verify-mock-generation.py

# 4) browser flow: Vite on :5175 with PROXY_CODEGEN_BACKEND=http://127.0.0.1:7003
#    then Text tab -> prompt -> Generate -> editor shows the scripted page
```
Verified 2026-09-05: PASS at every layer (SSE parse, tool execution, file
state, finalize, Vite proxy, live UI iframe rendering).

## E2E generation test (verified 2026-09-05)
`scripts/test-generation-ws.py` drives the full WebSocket pipeline:
```bash
cd backend && GEMINI_KEY=<key> poetry run python ../scripts/test-generation-ws.py \
  ws://127.0.0.1:7002 --save
```
Result: PASS - complete 160KB Tailwind page generated; also verified live in
the app UI (Text tab -> Generate -> rendered preview with all requested
content).

## Transitional state (until next reboot)
The long-running backend on 7001 started BEFORE the key existed and resists
termination (access denied from this session). Workaround in place:
- Backend with key runs on **7002** (test/preview use)
- Frontend dev on **5174** proxies to 7002 (registered preview)
- Old stack still on 5173/7001 until reboot
After a reboot the startup script recreates everything aligned on
5173/7001 with the key loaded - no manual steps.

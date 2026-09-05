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

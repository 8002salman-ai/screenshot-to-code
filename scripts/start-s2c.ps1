# =============================================================================
# Screenshot-to-code: full local stack + Vercel auto-sync
# Starts: 1) FastAPI backend (:7001)  2) Vite frontend (:5173)
#         3) Cloudflare tunnel (permanent named tunnel, quick-tunnel fallback)
# Then:   Verifies the deployed Vercel frontend points at the live backend URL.
#         If the URL drifted (tunnel URL changed), updates Vercel env vars and
#         redeploys automatically.
# Logs:   C:\AI-LAB\screenshot-to-code\logs\  (backend/frontend/cloudflared/status)
# Run at: Windows login (Startup folder -> s2c-startup.bat)
# Usage:  start-s2c.ps1 [-ForceSync]   (-ForceSync re-pushes env vars + redeploys
#                                      Vercel even without drift)
# =============================================================================
param([switch]$ForceSync)

$ErrorActionPreference = "Continue"

$Root        = "C:\AI-LAB\screenshot-to-code"
$Log         = "$Root\logs"
$FrontendDir = "$Root\frontend"
$BackendDir  = "$Root\backend"

# --- Tool paths -------------------------------------------------------------
$Poetry      = "C:\Users\basco\AppData\Local\Programs\Python\Python312\Scripts\poetry.exe"
$Cloudflared = "C:\Program Files (x86)\cloudflared\cloudflared.exe"
$TunnelName  = "s2c-backend"
$TunnelCfg   = "C:\Users\basco\.cloudflared\s2c-backend.yml"
$QuickTunnelCfg = "$Root\s2c-cloudflared-ingress.yml"   # overrides stale ~/.cloudflared/config.yml

# --- Deployed frontend (used for the Vercel drift check) --------------------
$VercelProdUrl      = "https://frontend-kohl-gamma-12.vercel.app"
$DesiredBackendUrl  = "https://s2c.luxedge.us"           # permanent tunnel URL

# Force UTF-8 so Unicode prints never crash on Windows legacy codepages
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"

New-Item -ItemType Directory -Force -Path $Log | Out-Null

function Log([string]$msg) {
  Add-Content "$Log\status.log" "$(Get-Date -Format s) $msg"
}

function Test-PortListening([int]$port) {
  return [bool](Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue)
}

function Test-UrlHealthy([string]$url, [int]$timeoutSec = 8) {
  try {
    $r = Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec $timeoutSec
    return ($r.StatusCode -ge 200 -and $r.StatusCode -lt 300)
  } catch { return $false }
}

function Start-Backend {
  if (Test-PortListening 7001) { Log "backend: already listening on 7001, skipping start"; return }
  Start-Process -WindowStyle Hidden -FilePath $Poetry `
    -ArgumentList 'run','uvicorn','main:app','--host','127.0.0.1','--port','7001' `
    -WorkingDirectory $BackendDir `
    -RedirectStandardOutput "$Log\backend.log" -RedirectStandardError "$Log\backend.err.log"
  Log "backend: start requested"
}

function Start-FrontendDev {
  if (Test-PortListening 5173) { Log "frontend: already listening on 5173, skipping start"; return }
  # Route through cmd so pnpm resolves from the user's PATH regardless of shell
  Start-Process -WindowStyle Hidden -FilePath "cmd.exe" `
    -ArgumentList '/c','pnpm','dev' `
    -WorkingDirectory $FrontendDir `
    -RedirectStandardOutput "$Log\frontend.log" -RedirectStandardError "$Log\frontend.err.log"
  Log "frontend: start requested (pnpm dev on 5173)"
}

function Start-NamedTunnel {
  if (Get-Process cloudflared -ErrorAction SilentlyContinue) {
    Log "tunnel: cloudflared already running, skipping start"
    return
  }
  Start-Process -WindowStyle Hidden -FilePath $Cloudflared `
    -ArgumentList 'tunnel','--config',$TunnelCfg,'run',$TunnelName `
    -RedirectStandardOutput "$Log\cloudflared.log" -RedirectStandardError "$Log\cloudflared.err.log"
  Log "tunnel: named tunnel '$TunnelName' start requested"
}

function Start-QuickTunnel {
  Log "tunnel: FALLBACK to quick tunnel (named tunnel unreachable)"
  Get-Process cloudflared -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
  Start-Sleep -Seconds 2
  Remove-Item "$Log\cloudflared.log","$Log\cloudflared.err.log" -Force -ErrorAction SilentlyContinue
  Start-Process -WindowStyle Hidden -FilePath $Cloudflared `
    -ArgumentList 'tunnel','--url','http://127.0.0.1:7001','--config',$QuickTunnelCfg,'--protocol','http2' `
    -RedirectStandardOutput "$Log\cloudflared.log" -RedirectStandardError "$Log\cloudflared.err.log"
  # Wait for the random URL to appear in the log
  foreach ($i in 1..20) {
    Start-Sleep -Seconds 2
    $content = (Get-Content "$Log\cloudflared.log","$Log\cloudflared.err.log" -Raw -ErrorAction SilentlyContinue) -join "`n"
    if ($content -match 'https://[a-z0-9-]+\.trycloudflare\.com') {
      $url = $Matches[0]
      Log "tunnel: quick tunnel up at $url"
      return $url
    }
  }
  Log "tunnel: quick tunnel FAILED to produce a URL"
  return $null
}

function Get-DeployedBackendUrl {
  # Returns the backend URL baked into the deployed Vercel bundle, or $null.
  try {
    $html = (Invoke-WebRequest -Uri $VercelProdUrl -UseBasicParsing -TimeoutSec 20).Content
    if ($html -match 'assets/(index-[^"]+\.js)') {
      $jsUrl = "$VercelProdUrl/assets/$($Matches[1])"
      $js = (Invoke-WebRequest -Uri $jsUrl -UseBasicParsing -TimeoutSec 30).Content
      if ($js -match 'https://[a-z0-9.-]+(?:trycloudflare\.com|luxedge\.us)') { return $Matches[0] }
    }
  } catch {
    Log "vercel-check: could not inspect deployed bundle: $($_.Exception.Message)"
  }
  return $null
}

function Sync-VercelBackendUrl([string]$httpUrl) {
  $wsUrl = $httpUrl -replace '^http','ws'
  Log "vercel-sync: updating env vars to $httpUrl / $wsUrl and redeploying..."
  Push-Location $FrontendDir
  try {
    foreach ($target in 'production','preview','development') {
      & vercel env rm VITE_HTTP_BACKEND_URL $target --yes 2>$null | Out-Null
      & vercel env rm VITE_WS_BACKEND_URL $target --yes 2>$null | Out-Null
      # 'preview' requires an explicit (empty) git-branch argument or the CLI
      # prompts interactively; production/development do not.
      $branchArg = @(); if ($target -eq 'preview') { $branchArg = @('') }
      $httpUrl  | & vercel env add VITE_HTTP_BACKEND_URL $target @branchArg 2>$null | Out-Null
      $wsUrl    | & vercel env add VITE_WS_BACKEND_URL   $target @branchArg 2>$null | Out-Null
    }
    $deployOut = & vercel deploy --prod --yes 2>&1 | Select-Object -Last 5
    Log ("vercel-sync: deploy output: " + (($deployOut -join ' | ') -replace '\s+', ' '))
  } catch {
    Log "vercel-sync: ERROR $($_.Exception.Message)"
  } finally { Pop-Location }
}

# ============================ MAIN ==========================================

Log "===== start-s2c beginning ====="

Start-Backend
Start-FrontendDev
Start-NamedTunnel

# Wait for the permanent tunnel (up to ~90s)
$effectiveUrl = $null
foreach ($i in 1..30) {
  Start-Sleep -Seconds 3
  if (Test-UrlHealthy "$DesiredBackendUrl/api/capabilities") { $effectiveUrl = $DesiredBackendUrl; break }
}

if (-not $effectiveUrl) {
  $quick = Start-QuickTunnel
  if ($quick) {
    $effectiveUrl = $quick
    foreach ($i in 1..15) {
      Start-Sleep -Seconds 2
      if (Test-UrlHealthy "$effectiveUrl/api/capabilities") { break }
    }
  }
}

if ($effectiveUrl) {
  Log "backend+tunnel UP at $effectiveUrl"
} else {
  Log "backend+tunnel DOWN - no usable tunnel URL (local dev still available)"
}

# --- Vercel drift check + auto-sync -----------------------------------------
if ($effectiveUrl) {
  $deployedUrl = Get-DeployedBackendUrl
  if ($ForceSync) {
    Log "vercel-check: -ForceSync requested - re-syncing env vars + redeploying"
    Sync-VercelBackendUrl $effectiveUrl
  } elseif ($null -eq $deployedUrl) {
    Log "vercel-check: deployed URL unknown (inspection failed) - forcing sync to be safe"
    Sync-VercelBackendUrl $effectiveUrl
  } elseif ($deployedUrl -ne $effectiveUrl) {
    Log "vercel-check: DRIFT detected (deployed=$deployedUrl live=$effectiveUrl)"
    Sync-VercelBackendUrl $effectiveUrl
  } else {
    Log "vercel-check: OK - deployed bundle matches live backend URL"
  }
}

# --- Local frontend health (Vite can take ~30s on cold start) ----------------
$frontendUp = $false
foreach ($i in 1..9) {
  if (Test-UrlHealthy "http://localhost:5173" 5) { $frontendUp = $true; break }
  Start-Sleep -Seconds 5
}
if ($frontendUp) { Log "frontend: 5173 UP" }
else { Log "frontend: 5173 not responding after 45s - check logs\frontend.err.log" }

Log "===== start-s2c finished ====="

# Start the Pack It Up demo on this laptop: the API (laptop-only) and the named
# Cloudflare tunnel that serves it at https://packitup.temperedanalytics.com/.
# Each runs in its own minimized window; close the window to stop it.
# The tunnel needs %USERPROFILE%\.cloudflared\pack-it-up.yml and its credentials file (never committed).
$repo = $PSScriptRoot
$py = Join-Path $repo ".venv\Scripts\python.exe"
Start-Process -FilePath $py -ArgumentList "-m", "uvicorn", "backend.app:app", "--host", "127.0.0.1", "--port", "8000" `
    -WorkingDirectory $repo -WindowStyle Minimized
$cf = "C:\Program Files (x86)\cloudflared\cloudflared.exe"
$cfg = Join-Path $env:USERPROFILE ".cloudflared\pack-it-up.yml"
Start-Process -FilePath $cf -ArgumentList "tunnel", "--no-autoupdate", "--config", "`"$cfg`"", "run", "pack-it-up" -WindowStyle Minimized
Write-Host "Started. Check: https://packitup.temperedanalytics.com/health"

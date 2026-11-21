# Pack It Up demo on this laptop: the API (laptop-only, port 8000) and the named Cloudflare tunnel
# that serves it at https://packitup.temperedanalytics.com/.
#
#   run_demo.ps1              start the keeper (if it is not running) and show the status
#   run_demo.ps1 -Status      show what is running
#   run_demo.ps1 -RestartApi  stop the API; the keeper starts it again with the code on disk
#   run_demo.ps1 -Stop        stop the keeper, the API and the tunnel
#
# The keeper is this script run with -Watch in a hidden process. Every 10 seconds it starts the API or
# the tunnel if either is not running. It is started through Win32_Process.Create, so it does not belong
# to the terminal or the agent session that ran this script and keeps going when that closes. It does
# not survive a reboot or a sign-out: run this script again after one.
#
# Logs are in .cache\demo\ (git-ignored): keeper.log, and one output file per API or tunnel start.
# The tunnel needs %USERPROFILE%\.cloudflared\pack-it-up.yml and its credentials file (never committed).
param(
    [switch]$Watch,
    [switch]$Status,
    [switch]$RestartApi,
    [switch]$Stop
)

$repo = $PSScriptRoot
$port = 8000
$py = Join-Path $repo ".venv\Scripts\python.exe"
$cf = "C:\Program Files (x86)\cloudflared\cloudflared.exe"
$cfg = Join-Path ([Environment]::GetFolderPath("UserProfile")) ".cloudflared\pack-it-up.yml"
$logDir = Join-Path $repo ".cache\demo"
$publicHealth = "https://packitup.temperedanalytics.com/health"
$checkSeconds = 10

function Get-Keeper {
    Get-CimInstance Win32_Process -Filter "Name='powershell.exe'" |
        Where-Object { $_.ProcessId -ne $PID -and $_.CommandLine -like "*-File*run_demo.ps1* -Watch*" }
}
function Get-ApiProcs {
    Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
        Where-Object { $_.CommandLine -like "*uvicorn backend.app:app*--port $port*" }
}
function Get-TunnelProcs {
    Get-CimInstance Win32_Process -Filter "Name='cloudflared.exe'" |
        Where-Object { $_.CommandLine -like "*run pack-it-up*" }
}
function Test-ApiListening {
    [bool](Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue)
}
function Test-Url([string]$url) {
    try { (Invoke-WebRequest -UseBasicParsing -TimeoutSec 8 -Uri $url).StatusCode -eq 200 } catch { $false }
}
function Write-KeeperLog([string]$text) {
    Add-Content -Path (Join-Path $logDir "keeper.log") -Value ("{0}  {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $text) -Encoding utf8
}
function Start-Api {
    $stamp = Get-Date -Format "HHmmss"
    Start-Process -FilePath $py -ArgumentList "-m", "uvicorn", "backend.app:app", "--host", "127.0.0.1", "--port", "$port" `
        -WorkingDirectory $repo -WindowStyle Hidden `
        -RedirectStandardOutput (Join-Path $logDir "api-$stamp.out.log") `
        -RedirectStandardError (Join-Path $logDir "api-$stamp.err.log")
    Write-KeeperLog "started the API (output in api-$stamp.*.log)"
}
function Start-Tunnel {
    $stamp = Get-Date -Format "HHmmss"
    Start-Process -FilePath $cf -ArgumentList "tunnel", "--no-autoupdate", "--config", "`"$cfg`"", "run", "pack-it-up" `
        -WorkingDirectory $repo -WindowStyle Hidden `
        -RedirectStandardOutput (Join-Path $logDir "tunnel-$stamp.out.log") `
        -RedirectStandardError (Join-Path $logDir "tunnel-$stamp.err.log")
    Write-KeeperLog "started the tunnel (output in tunnel-$stamp.*.log)"
}
function Show-Status {
    $keeper = @(Get-Keeper)
    $api = @(Get-ApiProcs)
    $tunnel = @(Get-TunnelProcs)
    if ($keeper.Count) { "Keeper:  running (pid $($keeper[0].ProcessId))" } else { "Keeper:  NOT running; nothing will restart the API or the tunnel" }
    if ($api.Count) { "API:     running (pid $(($api | ForEach-Object { $_.ProcessId }) -join ', ')), port $port listening: $(Test-ApiListening)" } else { "API:     NOT running" }
    if ($tunnel.Count) { "Tunnel:  running (pid $($tunnel[0].ProcessId))" } else { "Tunnel:  NOT running" }
    "Laptop:  http://127.0.0.1:$port/health answers: $(Test-Url "http://127.0.0.1:$port/health")"
    "Public:  $publicHealth answers: $(Test-Url $publicHealth)"
}

# ---------- the keeper loop (run by this script, not by hand) ----------
if ($Watch) {
    $isNew = $false
    $mutex = New-Object System.Threading.Mutex($true, "Global\PackItUpDemoKeeper", [ref]$isNew)
    if (-not $isNew) { exit 0 }   # another keeper already has it
    New-Item -ItemType Directory -Force $logDir | Out-Null
    Write-KeeperLog "keeper started (pid $PID)"
    # After a start, skip two checks for that process so a slow start is not taken for a missing one.
    $apiSkip = 0
    $tunnelSkip = 0
    while ($true) {
        try {
            if ($apiSkip -gt 0) { $apiSkip-- }
            elseif (-not (Get-ApiProcs) -and -not (Test-ApiListening)) { Start-Api; $apiSkip = 2 }
            if ($tunnelSkip -gt 0) { $tunnelSkip-- }
            elseif (-not (Get-TunnelProcs)) { Start-Tunnel; $tunnelSkip = 2 }
        } catch {
            try { Write-KeeperLog "error: $_" } catch { }
        }
        Start-Sleep -Seconds $checkSeconds
    }
}

if ($Status) { Show-Status; exit 0 }

if ($Stop) {
    Get-Keeper | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
    Get-ApiProcs | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
    Get-TunnelProcs | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
    Start-Sleep -Seconds 1
    Show-Status
    exit 0
}

if ($RestartApi) {
    # A move that is being read when the API stops stays "still working"; check runs\*\status.json first.
    Get-ApiProcs | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
    "Stopped the API. The keeper starts it again within $checkSeconds seconds."
}

# ---------- start the keeper if it is not running ----------
if (-not (Get-Keeper)) {
    New-Item -ItemType Directory -Force $logDir | Out-Null
    $cmd = "powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$PSCommandPath`" -Watch"
    $made = Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{ CommandLine = $cmd; CurrentDirectory = $repo }
    if ($made.ReturnValue -ne 0) { Write-Error "Could not start the keeper (Win32_Process.Create returned $($made.ReturnValue))."; exit 1 }
    "Started the keeper (pid $($made.ProcessId))."
}

# Wait for the laptop address, then show where things stand.
$deadline = (Get-Date).AddSeconds(60)
while ((Get-Date) -lt $deadline -and -not (Test-Url "http://127.0.0.1:$port/health")) { Start-Sleep -Seconds 2 }
Show-Status

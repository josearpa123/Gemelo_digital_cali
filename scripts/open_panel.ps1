# Runs on Windows from start_panel.sh, so readiness includes WSL port forwarding.
param(
    [string]$Url = 'http://localhost:8000',
    [int]$MaxSeconds = 120,
    [switch]$NoBrowser
)
$ErrorActionPreference = 'Stop'
$watch = [Diagnostics.Stopwatch]::StartNew()
Write-Host 'Esperando la conexion desde Windows...'
while ($watch.Elapsed.TotalSeconds -lt $MaxSeconds) {
    try {
        $response = Invoke-WebRequest -Uri "$Url/health" -UseBasicParsing -TimeoutSec 3
        $health = $response.Content | ConvertFrom-Json
        if ($health.status -eq 'ok' -and $health.sumo -like 'Eclipse SUMO*') {
            Write-Host "Panel disponible: $Url"
            if (-not $NoBrowser) { Start-Process -FilePath $Url }
            exit 0
        }
    } catch { }
    Start-Sleep -Seconds 1
}
Write-Error "El panel no respondio desde Windows en $MaxSeconds segundos. Revisa los logs de Docker."
exit 1

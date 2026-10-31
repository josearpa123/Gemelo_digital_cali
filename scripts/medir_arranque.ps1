# Measures the time from `docker compose up -d --build` until the panel answers on
# http://localhost:8000 (the "Prueba del companero" in the README). Windows PowerShell 5+ / 7.
# Usage: powershell -ExecutionPolicy Bypass -File scripts\medir_arranque.ps1 [-Url http://localhost:8000] [-MaxMinutes 30]
param(
  [string]$Url = "http://localhost:8000",
  [int]$MaxMinutes = 30
)
$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")

$watch = [System.Diagnostics.Stopwatch]::StartNew()
Write-Host ("[{0:HH:mm:ss}] docker compose up -d --build sim-api" -f (Get-Date))
docker compose up -d --build sim-api
if ($LASTEXITCODE -ne 0) { Write-Error "docker compose fallo (esta abierto Docker Desktop?)"; exit 1 }

Write-Host ("[{0:HH:mm:ss}] esperando a $Url ..." -f (Get-Date))
while ($true) {
  try {
    $page = Invoke-WebRequest -Uri "$Url/" -UseBasicParsing -TimeoutSec 5
    $health = Invoke-RestMethod -Uri "$Url/health" -TimeoutSec 5
    if ($page.StatusCode -eq 200 -and $health.status -eq "ok") { break }
  } catch { }
  if ($watch.Elapsed.TotalMinutes -gt $MaxMinutes) {
    Write-Error "No respondio en $MaxMinutes minutos. Revisa: docker compose logs sim-api"
    exit 1
  }
  Start-Sleep -Seconds 2
}
$watch.Stop()
$s = [int]$watch.Elapsed.TotalSeconds
Write-Host ("La app respondio en {0} tras {1} s = {2} min {3:D2} s ({4:N1} minutos)" -f $Url, $s, [int][math]::Floor($s / 60), ($s % 60), $watch.Elapsed.TotalMinutes)

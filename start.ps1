# ============================================================
# Script de démarrage automatique - HUBapp_TEMPLATE (Windows)
# ============================================================
# Détecte automatiquement si le réseau Hub existe et configure
# l'application en conséquence.
#
# Usage:
#   .\start.ps1              # Démarrer
#   .\start.ps1 down         # Arrêter
#   .\start.ps1 logs         # Voir les logs
#   .\start.ps1 restart      # Redémarrer
# ============================================================

param(
    [Parameter(Position=0)]
    [string]$Command = "up",
    
    [Parameter(ValueFromRemainingArguments=$true)]
    [string[]]$RemainingArgs
)

$ErrorActionPreference = "Stop"

# Charger les variables d'environnement depuis .env si présent
if (Test-Path ".env") {
    Get-Content ".env" | ForEach-Object {
        if ($_ -match "^([^#][^=]+)=(.*)$") {
            [Environment]::SetEnvironmentVariable($matches[1], $matches[2], "Process")
        }
    }
}

$APP_NAME = if ($env:APP_SLUG) { $env:APP_SLUG } else { "mon-app" }
$HUB_NETWORK = "hub_hub-network"

# Fonction pour détecter si le réseau Hub existe
function Detect-HubNetwork {
    $networkExists = docker network inspect $HUB_NETWORK 2>$null
    if ($LASTEXITCODE -eq 0) {
        Write-Host "[OK] Reseau Hub detecte ($HUB_NETWORK)" -ForegroundColor Green
        $env:HUB_NETWORK_EXTERNAL = "true"
        $env:HUB_NETWORK_NAME = $HUB_NETWORK
        return $true
    } else {
        Write-Host "[!] Reseau Hub non trouve, creation d'un reseau local" -ForegroundColor Yellow
        $env:HUB_NETWORK_EXTERNAL = "false"
        $env:HUB_NETWORK_NAME = "$APP_NAME-hub-network"
        return $false
    }
}

# Afficher le header
Write-Host "================================================" -ForegroundColor Blue
Write-Host "  HUBapp_TEMPLATE - $APP_NAME" -ForegroundColor Blue
Write-Host "================================================" -ForegroundColor Blue

switch ($Command.ToLower()) {
    { $_ -in "up", "start" } {
        Detect-HubNetwork | Out-Null
        Write-Host "[>] Demarrage de l'application..." -ForegroundColor Blue
        docker-compose up -d @RemainingArgs
        Write-Host "[OK] Application demarree !" -ForegroundColor Green
        Write-Host ""
        $frontendPort = if ($env:FRONTEND_PORT) { $env:FRONTEND_PORT } else { "4250" }
        $apiPort = if ($env:API_PORT) { $env:API_PORT } else { "9045" }
        Write-Host "  Frontend : http://localhost:$frontendPort"
        Write-Host "  API      : http://localhost:$apiPort/api/docs"
    }
    { $_ -in "down", "stop" } {
        Write-Host "[>] Arret de l'application..." -ForegroundColor Blue
        docker-compose down @RemainingArgs
        Write-Host "[OK] Application arretee" -ForegroundColor Green
    }
    "restart" {
        Detect-HubNetwork | Out-Null
        Write-Host "[>] Redemarrage de l'application..." -ForegroundColor Blue
        docker-compose down
        docker-compose up -d @RemainingArgs
        Write-Host "[OK] Application redemarree !" -ForegroundColor Green
    }
    "logs" {
        docker-compose logs -f @RemainingArgs
    }
    "build" {
        Detect-HubNetwork | Out-Null
        Write-Host "[>] Build de l'application..." -ForegroundColor Blue
        docker-compose build @RemainingArgs
        Write-Host "[OK] Build termine" -ForegroundColor Green
    }
    "status" {
        Detect-HubNetwork | Out-Null
        Write-Host ""
        docker-compose ps
    }
    default {
        Write-Host "Usage: .\start.ps1 {up|down|restart|logs|build|status}"
        Write-Host ""
        Write-Host "Commandes:"
        Write-Host "  up, start   - Demarrer l'application"
        Write-Host "  down, stop  - Arreter l'application"
        Write-Host "  restart     - Redemarrer l'application"
        Write-Host "  logs        - Afficher les logs (suivis)"
        Write-Host "  build       - Reconstruire les images"
        Write-Host "  status      - Afficher l'etat des services"
        exit 1
    }
}

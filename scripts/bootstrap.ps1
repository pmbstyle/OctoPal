Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if (-not (Test-Path "pyproject.toml")) {
    Write-Error "Run this script from the repository root (pyproject.toml not found)."
}

function Test-Uv {
    return [bool](Get-Command uv -ErrorAction SilentlyContinue)
}

function Test-Npm {
    return [bool](Get-Command npm -ErrorAction SilentlyContinue)
}

function Install-NodeJs {
    if ((Test-Npm) -and (Get-Command node -ErrorAction SilentlyContinue)) {
        $currentMajor = (& node -p "process.versions.node.split('.')[0]")
        if ([int]$currentMajor -ge 20) {
            return
        }
    }

    Write-Host "Node.js 20+ and npm are required. Installing/upgrading..."

    if (Get-Command winget -ErrorAction SilentlyContinue) {
        winget install --exact --id OpenJS.NodeJS.LTS --accept-package-agreements --accept-source-agreements
    }
    elseif (Get-Command choco -ErrorAction SilentlyContinue) {
        choco install nodejs-lts -y
    }
    else {
        throw "Could not auto-install Node.js/npm. Install Node.js LTS manually, restart PowerShell, and rerun .\scripts\bootstrap.ps1."
    }

    $machineNodePath = "${env:ProgramFiles}\nodejs"
    if ((Test-Path $machineNodePath) -and ($env:Path -notlike "*$machineNodePath*")) {
        $env:Path = "$machineNodePath;$env:Path"
    }

    if ((-not (Test-Npm)) -or (-not (Get-Command node -ErrorAction SilentlyContinue))) {
        throw "Node.js/npm installation finished, but node or npm is still not on PATH. Restart PowerShell and rerun .\scripts\bootstrap.ps1."
    }

    $installedMajor = (& node -p "process.versions.node.split('.')[0]")
    if ([int]$installedMajor -lt 20) {
        throw "Node.js 20 or newer is required for the WhatsApp bridge. Found $(& node --version)."
    }
}

if (-not (Test-Uv)) {
    Write-Host "uv not found. Installing..."
    powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
}

if (-not (Test-Uv)) {
    $localUvPath = Join-Path $HOME ".local\bin"
    if (Test-Path $localUvPath) {
        $env:Path = "$localUvPath;$env:Path"
        
        # Persist to User PATH
        $currentPath = [Environment]::GetEnvironmentVariable("Path", "User")
        if ($currentPath -notlike "*$localUvPath*") {
            Write-Host "Adding $localUvPath to User PATH persistently..."
            [Environment]::SetEnvironmentVariable("Path", "$currentPath;$localUvPath", "User")
        }
    }
}

if (-not (Test-Uv)) {
    Write-Error "uv is still not available on PATH. Restart your shell and retry."
}

uv --version
uv sync

Write-Host "Installing Playwright browser binaries..."
uv run playwright install chromium

Install-NodeJs

Write-Host "Installing WhatsApp bridge dependencies..."
Push-Location "scripts/whatsapp_bridge"
try {
    npm install
}
finally {
    Pop-Location
}

Write-Host ""
Write-Host "Launching onboarding..."
uv run octopal configure

Write-Host ""
Write-Host "Bootstrap complete."
Write-Host "Next steps:"
Write-Host "  uv run octopal start"

# SOC Report Review Tool - Startup Script
# This script starts both the backend API and frontend web server

Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "SOC Report Review Tool - MVP Launcher" -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host ""

# Get the script directory
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$backendDir = Join-Path $scriptDir "backend"
$frontendDir = Join-Path $scriptDir "frontend"

# Colors for output
$success = "Green"
$error = "Red"
$info = "Yellow"

# Function to check if a port is in use
function Test-Port {
    param([int]$Port)
    $connection = New-Object System.Net.Sockets.TcpClient
    try {
        $connection.Connect("127.0.0.1", $Port)
        return $true
    } catch {
        return $false
    }
}

# Check if ports are available
Write-Host "Checking ports..." -ForegroundColor $info
if (Test-Port 5000) {
    Write-Host "⚠️  Port 5000 is already in use. Attempting to free it..." -ForegroundColor $error
    Get-Process -Name python -ErrorAction SilentlyContinue | Stop-Process -Force
    Start-Sleep 2
}

if (Test-Port 8000) {
    Write-Host "⚠️  Port 8000 is already in use. Attempting to free it..." -ForegroundColor $error
    Get-Process -Name python -ErrorAction SilentlyContinue | Stop-Process -Force
    Start-Sleep 2
}

Write-Host "✓ Ports available" -ForegroundColor $success
Write-Host ""

# Check if Ollama is running
Write-Host "Checking Ollama..." -ForegroundColor $info
try {
    $response = Invoke-WebRequest -Uri "http://localhost:11434/api/tags" -ErrorAction SilentlyContinue
    Write-Host "✓ Ollama is running" -ForegroundColor $success
} catch {
    Write-Host "⚠️  Ollama is not running. Please start Ollama first:" -ForegroundColor $error
    Write-Host "   Run: ollama serve" -ForegroundColor $info
    Write-Host ""
}

Write-Host ""

# Start Backend
Write-Host "Starting Backend API..." -ForegroundColor $info
$backendProcess = Start-Process -FilePath python `
    -ArgumentList "app.py" `
    -WorkingDirectory $backendDir `
    -PassThru `
    -NoNewWindow

Start-Sleep 3
Write-Host "✓ Backend API started on http://127.0.0.1:5000" -ForegroundColor $success

# Start Frontend
Write-Host "Starting Frontend Server..." -ForegroundColor $info
$frontendProcess = Start-Process -FilePath python `
    -ArgumentList "-m", "http.server", "8000", "--bind", "127.0.0.1" `
    -WorkingDirectory $frontendDir `
    -PassThru `
    -NoNewWindow

Start-Sleep 2
Write-Host "✓ Frontend Server started on http://127.0.0.1:8000" -ForegroundColor $success

Write-Host ""
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "✓ SOC Report Review Tool is ready!" -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Frontend: http://127.0.0.1:8000" -ForegroundColor $success
Write-Host "Backend API: http://127.0.0.1:5000" -ForegroundColor $success
Write-Host ""
Write-Host "Press Ctrl+C to stop all services" -ForegroundColor $info
Write-Host ""

# Wait for user to stop
try {
    while ($true) {
        Start-Sleep 1
    }
} catch {
    Write-Host "Shutting down..." -ForegroundColor $info
}

# Cleanup
Write-Host "Stopping services..." -ForegroundColor $info
Stop-Process -Id $backendProcess.Id -Force -ErrorAction SilentlyContinue
Stop-Process -Id $frontendProcess.Id -Force -ErrorAction SilentlyContinue
Write-Host "✓ Services stopped" -ForegroundColor $success

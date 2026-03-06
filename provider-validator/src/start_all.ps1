# start_all.ps1 - Complete Application Startup Script
# Provider Validator - All Services Launcher

$ErrorActionPreference = "Stop"

Write-Host ""
Write-Host "============================================" -ForegroundColor Cyan
Write-Host "  PROVIDER VALIDATOR - STARTUP SCRIPT" -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""

# Check if virtual environment is activated
if (-not $env:VIRTUAL_ENV) {
    Write-Host "[ERROR] Virtual environment not activated!" -ForegroundColor Red
    Write-Host "Please run: .\venv\Scripts\Activate.ps1" -ForegroundColor Yellow
    Write-Host ""
    exit 1
}

Write-Host "[INFO] Virtual environment detected: $env:VIRTUAL_ENV" -ForegroundColor Green

# ============================================================================
# STEP 1: Check Redis
# ============================================================================
Write-Host ""
Write-Host "[1/4] Checking Redis..." -ForegroundColor Cyan

try {
    $redis = Get-Process redis-server -ErrorAction SilentlyContinue
    if ($redis) {
        Write-Host "[OK] Redis already running (PID: $($redis.Id))" -ForegroundColor Green
    } else {
        Write-Host "[WARN] Redis not running. Attempting to start..." -ForegroundColor Yellow
        
        # Try to start Redis
        Start-Process redis-server -WindowStyle Hidden -ErrorAction Stop
        Start-Sleep -Seconds 2
        
        # Verify it started
        $redis = Get-Process redis-server -ErrorAction SilentlyContinue
        if ($redis) {
            Write-Host "[OK] Redis started successfully (PID: $($redis.Id))" -ForegroundColor Green
        } else {
            throw "Redis failed to start"
        }
    }
    
    # Test Redis connection
    $pingResult = redis-cli ping 2>&1
    if ($pingResult -match "PONG") {
        Write-Host "[OK] Redis connection verified (localhost:6379)" -ForegroundColor Green
    } else {
        throw "Redis not responding to ping"
    }
} catch {
    Write-Host "[ERROR] Redis setup failed: $($_.Exception.Message)" -ForegroundColor Red
    Write-Host "[HELP] Install Redis: https://redis.io/download" -ForegroundColor Yellow
    Write-Host "       Or use WSL: wsl sudo service redis-server start" -ForegroundColor Yellow
    exit 1
}

# ============================================================================
# STEP 2: Start Celery Worker
# ============================================================================
Write-Host ""
Write-Host "[2/4] Starting Celery Worker..." -ForegroundColor Cyan

try {
    $celeryJob = Start-Job -ScriptBlock {
        Set-Location $using:PWD
        & "$using:PWD\venv\Scripts\Activate.ps1"
        celery -A src.celery_app.celery_app worker --loglevel=info --pool=solo
    }
    
    Start-Sleep -Seconds 5
    
    # Check if job is still running
    $jobState = (Get-Job -Id $celeryJob.Id).State
    if ($jobState -eq "Running") {
        Write-Host "[OK] Celery Worker started (Job ID: $($celeryJob.Id))" -ForegroundColor Green
    } else {
        throw "Celery Worker failed to start"
    }
} catch {
    Write-Host "[ERROR] Celery setup failed: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}

# ============================================================================
# STEP 3: Start FastAPI Server
# ============================================================================
Write-Host ""
Write-Host "[3/4] Starting FastAPI Server..." -ForegroundColor Cyan

try {
    $fastapiJob = Start-Job -ScriptBlock {
        Set-Location $using:PWD
        & "$using:PWD\venv\Scripts\Activate.ps1"
        uvicorn src.api.app:app --reload --port 8000
    }
    
    Start-Sleep -Seconds 7
    
    # Check if API is responding
    try {
        $response = Invoke-WebRequest -Uri "http://127.0.0.1:8000/" -TimeoutSec 5 -UseBasicParsing
        Write-Host "[OK] FastAPI Server running at http://127.0.0.1:8000" -ForegroundColor Green
        Write-Host "     API Docs: http://127.0.0.1:8000/docs" -ForegroundColor Gray
    } catch {
        Write-Host "[WARN] FastAPI may still be starting..." -ForegroundColor Yellow
    }
} catch {
    Write-Host "[ERROR] FastAPI setup failed: $($_.Exception.Message)" -ForegroundColor Red
    Stop-Job -Job $celeryJob -ErrorAction SilentlyContinue
    Remove-Job -Job $celeryJob -ErrorAction SilentlyContinue
    exit 1
}

# ============================================================================
# STEP 4: Start Gradio UI
# ============================================================================
Write-Host ""
Write-Host "[4/4] Starting Gradio UI..." -ForegroundColor Cyan
Write-Host ""
Write-Host "============================================" -ForegroundColor Green
Write-Host "  ALL SERVICES RUNNING!" -ForegroundColor Green
Write-Host "============================================" -ForegroundColor Green
Write-Host ""
Write-Host "Service Status:" -ForegroundColor Cyan
Write-Host "  [1] Redis:    Running on localhost:6379" -ForegroundColor White
Write-Host "  [2] Celery:   Job ID $($celeryJob.Id)" -ForegroundColor White
Write-Host "  [3] FastAPI:  http://127.0.0.1:8000" -ForegroundColor White
Write-Host "  [4] Gradio:   Starting at http://127.0.0.1:7860" -ForegroundColor White
Write-Host ""
Write-Host "Access Points:" -ForegroundColor Cyan
Write-Host "  - Gradio UI:   http://127.0.0.1:7860" -ForegroundColor Yellow
Write-Host "  - API Docs:    http://127.0.0.1:8000/docs" -ForegroundColor Yellow
Write-Host "  - API Health:  http://127.0.0.1:8000/" -ForegroundColor Yellow
Write-Host ""
Write-Host "Login Credentials:" -ForegroundColor Cyan
Write-Host "  Username: admin" -ForegroundColor Yellow
Write-Host "  Password: admin123" -ForegroundColor Yellow
Write-Host ""
Write-Host "Press Ctrl+C to stop all services" -ForegroundColor Gray
Write-Host "============================================" -ForegroundColor Green
Write-Host ""

# Start Gradio in foreground (blocks until Ctrl+C)
try {
    python src/gradio_app.py
} catch {
    Write-Host ""
    Write-Host "[INFO] Gradio stopped" -ForegroundColor Yellow
} finally {
    # ========================================================================
    # CLEANUP ON EXIT
    # ========================================================================
    Write-Host ""
    Write-Host "============================================" -ForegroundColor Yellow
    Write-Host "  SHUTTING DOWN SERVICES" -ForegroundColor Yellow
    Write-Host "============================================" -ForegroundColor Yellow
    
    Write-Host "[INFO] Stopping Celery Worker..." -ForegroundColor Cyan
    Stop-Job -Job $celeryJob -ErrorAction SilentlyContinue
    Remove-Job -Job $celeryJob -Force -ErrorAction SilentlyContinue
    
    Write-Host "[INFO] Stopping FastAPI Server..." -ForegroundColor Cyan
    Stop-Job -Job $fastapiJob -ErrorAction SilentlyContinue
    Remove-Job -Job $fastapiJob -Force -ErrorAction SilentlyContinue
    
    Write-Host "[INFO] Stopping Redis (optional)..." -ForegroundColor Cyan
    # Uncomment next line if you want to stop Redis on exit
    # Stop-Process -Name redis-server -Force -ErrorAction SilentlyContinue
    
    Write-Host ""
    Write-Host "[OK] All services stopped" -ForegroundColor Green
    Write-Host ""
}
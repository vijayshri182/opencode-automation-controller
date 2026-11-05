param(
    [Parameter(Mandatory=$true)][string]$TargetDir,
    [string]$DevBranch = "dev/phase-13",
    [string]$ProdBranch = "master",
    [string]$BackupDir = "",
    [switch]$SkipClone,
    [switch]$SkipVenv,
    [switch]$SkipTests
)

function Log($msg) { Write-Host "[FNO-INSTALL] $msg" }

if (-not (Test-Path $TargetDir)) { New-Item -ItemType Directory -Path $TargetDir -Force | Out-Null }
$repos = Join-Path $TargetDir "repos"
$logs = Join-Path $TargetDir "logs"
$validation = Join-Path $TargetDir "validation"
foreach ($d in $repos,$logs,$validation) { New-Item -ItemType Directory -Path $d -Force | Out-Null }

# Prereq check
$py = Get-Command python -ErrorAction SilentlyContinue
if (-not $py) { throw "Python not found on PATH" }
$git = Get-Command git -ErrorAction SilentlyContinue
if (-not $git) { throw "Git not found on PATH" }
Log "Prereqs OK: python=$($py.Source)"

if (-not $SkipClone) {
    Log "Cloning repositories..."
    if (-not (Test-Path "$repos\fno-ai-paper-trading")) {
        $ErrorActionPreference = "Continue"
        git clone https://github.com/vijayshri182/fno-ai-paper-trading.git "$repos\fno-ai-paper-trading" 2>&1 | Out-Null
        
    }
    if (-not (Test-Path "$repos\fno-ai-paper-trading-dev")) {
        $ErrorActionPreference = "Continue"
        git clone https://github.com/vijayshri182/fno-ai-paper-trading.git "$repos\fno-ai-paper-trading-dev" 2>&1 | Out-Null
        
    }
    $ErrorActionPreference = "Continue"
    Push-Location "$repos\fno-ai-paper-trading"; git checkout $ProdBranch 2>&1 | Out-Null; Pop-Location
    Push-Location "$repos\fno-ai-paper-trading-dev"; git checkout $DevBranch 2>&1 | Out-Null; Pop-Location
    
    Log "Clones checked out"
}

foreach ($r in "fno-ai-paper-trading","fno-ai-paper-trading-dev") {
    if (-not $SkipVenv) {
        $repoPath = "$repos\$r"
        if (-not (Test-Path $repoPath)) { Log "Repo missing for $r; skipping"; continue }
    if (-not (Test-Path "$repoPath\.venv")) {
            Log "Creating venv for $r"
            & python -m venv "$repoPath\.venv"
        }
        Log "Installing deps for $r"
        & "$repoPath\.venv\Scripts\pip.exe" install -r "$repoPath\requirements.txt" 2>&1 | Out-Null
    }
    # Create .env from template if missing
    if (-not (Test-Path "$repos\$r\.env") -and (Test-Path "$repos\$r\.env.example")) {
        Copy-Item "$repos\$r\.env.example" "$repos\$r\.env"
        Log "Created .env from template for $r (fill secrets manually)"
    }
}

if (-not $SkipTests) {
    Log "Running synthetic tests..."
    $env:PYTHONPATH = "$repos\fno-ai-paper-trading\src"
    & "$repos\fno-ai-paper-trading\.venv\Scripts\python.exe" -m pytest "$repos\fno-ai-paper-trading\tests\test_wp_prod_28_startup_readiness.py" "$repos\fno-ai-paper-trading\tests\test_wp_prod_29_startup_phase.py" -q 2>&1 | Out-File "$logs\test_prod.log"
    $env:PYTHONPATH = "$repos\fno-ai-paper-trading-dev\src"
    & "$repos\fno-ai-paper-trading-dev\.venv\Scripts\python.exe" -m pytest "$repos\fno-ai-paper-trading-dev\tests\test_wp_prod_28_startup_readiness.py" "$repos\fno-ai-paper-trading-dev\tests\test_wp_prod_29_startup_phase.py" -q 2>&1 | Out-File "$logs\test_dev.log"
    Log "Tests complete (see $logs)"
}

# Restore data from backup if provided
if ($BackupDir -and (Test-Path $BackupDir)) {
    Log "Restoring databases from $BackupDir..."
    $restoreDir = Join-Path $TargetDir "backup_restore"
    New-Item -ItemType Directory -Path "$restoreDir\databases" -Force | Out-Null
    foreach ($db in "prod_paper_trading.db","prod_gui_paper_trading.db") {
        $src = Join-Path $BackupDir "databases\$db"
        if (Test-Path $src) {
            Copy-Item $src "$restoreDir\databases\$db" -Force
            Log "Restored $db"
        }
    }
}

# Validate config (no secrets printed)
Log "Configuration validation: check .env has FNO_LIVE_EXECUTION_TEST_ENABLED=0"
foreach ($r in "fno-ai-paper-trading","fno-ai-paper-trading-dev") {
    $v = Select-String -Path "$repos\$r\.env" -Pattern '^FNO_LIVE_EXECUTION_TEST_ENABLED='
    if ($v) { Log "  $r : $($v.Line)" } else { Log "  $r : FNO_LIVE_EXECUTION_TEST_ENABLED not set (check template)" }
}

Log "Installation complete. See $logs and $validation."
Log "NEXT: establish central credential store via authorize_market_data_credential.py (interactive, operator-authorized)."

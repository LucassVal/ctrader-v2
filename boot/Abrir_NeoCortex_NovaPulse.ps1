param([switch]$Elevated)

# [GOVERNANCA] PROIBICAO ABSOLUTA


    Write-Host "  ----------------------------------------"
# O backfill Python tem handler proprio: Ctrl+C salva parcial e resume.
# Para encerrar completamente: feche a janela ou Ctrl+C 2x.

if (-not $Elevated) {
    Start-Process powershell -ArgumentList "-NoProfile -ExecutionPolicy Bypass -File `"$PSCommandPath`" -Elevated" -Verb RunAs
    exit
}

$NC_ROOT  = "C:\Workspace\Neocortex v44\neocortex"
$VENV_PY  = "$NC_ROOT\.venv\Scripts\python.exe"
$PID_FILE = "$NC_ROOT\.context\nc_boot.pids"
$NC_PORTS = @(7744, 5173)

Set-Location $NC_ROOT

# ── PYTHONPATH fix ──
$env:PYTHONPATH = $null

# ── LOG simples ──
$BOOT_LOG = "$env:USERPROFILE\Desktop\nc_boot.log"
"BOOT iniciado em $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')" | Out-File $BOOT_LOG
"PYTHONPATH=$env:PYTHONPATH" | Out-File $BOOT_LOG -Append

Write-Host "============================================================"
Write-Host " NEOCORTEX V44 -- BOOT SEQUENCE"
Write-Host " Log: $BOOT_LOG"
Write-Host "============================================================"

# -- PROGRESS TRACKER (R-PROGRESS + R-VISIBLE-RUN) --
$script:StepTotal = 0
$script:StepCurrent = 0
$script:PhaseStart = Get-Date

function Start-Phase([string]$Name, [int]$Total) {
    $script:StepTotal = $Total; $script:StepCurrent = 0
    $ts = Get-Date -Format 'HH:mm:ss'
    Write-Host ""; Write-Host "[$ts] --- $Name ($Total etapas) ---"
}
function Write-Step([string]$Label) {
    $script:StepCurrent++
    if ($script:StepTotal -eq 0) {
        $ts = Get-Date -Format "HH:mm:ss"
        Write-Host "[$ts]   [START] $Label"
        return
    }
    $pct = [math]::Round($script:StepCurrent / $script:StepTotal * 100)
    $bar = "#" * [math]::Floor($pct / 5) + "-" * (20 - [math]::Floor($pct / 5))
    $ts = Get-Date -Format 'HH:mm:ss'
    Write-Host "  [$ts] [$($script:StepCurrent)/$($script:StepTotal)] [$bar] $pct% $Label"
    # Forca flush do console (evita freeze visual)
    [System.Console]::Out.Flush()
}
function Complete-Phase {
    $elapsed = [math]::Round(((Get-Date) - $script:PhaseStart).TotalSeconds, 1)
    $ts = Get-Date -Format "HH:mm:ss"
    Write-Host "[$ts]   [OK] Fase concluida em ${elapsed}s"
}

$bootPids = [System.Collections.Generic.List[int]]::new()

# ─── HELPER: original simples (sem modificacoes) ──────
function Start-NC {
    param([string]$Title, [string]$Dir, [string]$Command)
    $scriptText = @"
try { `$Host.UI.RawUI.WindowTitle = "$Title" } catch {}
Set-Location -LiteralPath "$Dir"
$Command
"@
    $bytes   = [System.Text.Encoding]::Unicode.GetBytes($scriptText)
    $encoded = [Convert]::ToBase64String($bytes)
    $proc = Start-Process powershell `
        -ArgumentList @("-NoProfile", "-ExecutionPolicy", "Bypass", "-WindowStyle", "Hidden", "-EncodedCommand", $encoded) `
        -WindowStyle Hidden -PassThru
    if ($proc) { $script:bootPids.Add($proc.Id) }
}

# ─── HELPER: cmdline segura + identidade de processo do projeto ──
function Get-NCCmdLine {
    param([int]$ProcId)
    try {
        return (Get-CimInstance Win32_Process -Filter "ProcessId=$ProcId" -EA Stop).CommandLine
    } catch { return '' }
}

function Test-NCProcess {
    # True somente se o processo pertence ao projeto (Path ou CommandLine sob $NC_ROOT).
    # NUNCA classifica processo externo (Kimi, VS Code, etc.) como alvo.
    param([int]$ProcId)
    $cmd = Get-NCCmdLine -ProcId $ProcId
    if ($cmd -and $cmd -like "*$NC_ROOT*") { return $true }
    try {
        $p = Get-Process -Id $ProcId -EA Stop
        if ($p.Path -and $p.Path -like "$NC_ROOT*") { return $true }
    } catch {}
    return $false
}

    Write-Host "  ----------------------------------------"
Write-Host ""
Write-Host "Start-Phase 'BOOT PRE-FLIGHT' 6"
$ts = Get-Date -Format "HH:mm:ss"
Write-Host "[$ts] [PRE-FLIGHT] Verificando sistema..."
"$(Get-Date -Format 'HH:mm:ss') PRE-FLIGHT iniciado" | Out-File $BOOT_LOG -Append

$CTRADER = "$NC_ROOT\11.0_apps\ctrader"
$DASH    = "$NC_ROOT\10.0_ui_dash"
$REACT   = "$DASH\react-dashboard"

# Python
try { $v = & $VENV_PY --version 2>&1; Write-Host "  [OK] Python: $v"; "  [OK] Python: $v" | Out-File $BOOT_LOG -Append } catch { Write-Host "  [ERRO] Python"; "  [ERRO] Python" | Out-File $BOOT_LOG -Append }

# Node
try { $nv = & node --version 2>&1; Write-Host "  [OK] Node: $nv"; "  [OK] Node: $nv" | Out-File $BOOT_LOG -Append } catch { Write-Host "  [WARN] Node"; "  [WARN] Node" | Out-File $BOOT_LOG -Append }

# Dependencias (Python packages + ORQs)
try {
    $depOutput = & $VENV_PY "$NC_ROOT\check_deps.py" 2>$null
    if (-not $depOutput) { throw "check_deps.py nao retornou saida" }
    $depJson = $depOutput | ConvertFrom-Json
    if ($depJson.all_ok) {
        $vbtVer = $depJson.vectorbt.version
        $talibVer = $depJson.talib.version
        $talibPat = $depJson.talib.patterns
        $ts = Get-Date -Format "HH:mm:ss"
        Write-Host "[$ts]   [OK] Deps: vbt=$vbtVer talib=$talibVer ($talibPat patterns) ORQs=$($depJson.orquestradores.PSObject.Properties.Count) OK"
        "  [OK] Deps: vbt=$vbtVer talib=$talibVer ($talibPat patterns)" | Out-File $BOOT_LOG -Append
    } else {
        $ts = Get-Date -Format "HH:mm:ss"
        Write-Host "[$ts]   [ERRO] Deps: FALHOU" -ForegroundColor Red
        $depJson.actions | ForEach-Object { Write-Host "    $_" -ForegroundColor DarkRed }
        "  [ERRO] Deps FAIL" | Out-File $BOOT_LOG -Append
        Read-Host "ENTER para sair"
        exit 1
    }
} catch {
    # step done; Write-Host "  [ERRO] Deps checker falhou: $_" -ForegroundColor Red
    "  [ERRO] Deps checker: $_" | Out-File $BOOT_LOG -Append
    Read-Host "ENTER para sair"
    exit 1
}

# Criticos
@("routers\ctrader_v2.py","NC-10_dashboard_api.py","src\main.tsx","config.yaml") | ForEach-Object {
    $f = if ($_ -like "src\*") { "$REACT\$_" } elseif ($_ -eq "config.yaml") { "$CTRADER\$_" } else { "$DASH\$_" }
    if (Test-Path $f) { Write-Host "  [OK] $_"; "  [OK] $_" | Out-File $BOOT_LOG -Append } else { Write-Host "  [ERRO] $_"; "  [ERRO] $_" | Out-File $BOOT_LOG -Append }
}

# step done
Write-Step 'Parquet 7 simbolos'
    # Parquet 7 simbolos"
    # [OK] Parquet 7 simbolos")
# Parquet 5 mercados
$mercados = @("XAUUSD","EURUSD","GBPUSD","USDJPY","AUDUSD")
$allSymbols = $mercados + @("DXYUSD","VIXUSD")
$missingParquet = @()
$existingParquet = @()

foreach ($sym in $allSymbols) {
    $pf = "$CTRADER\data\consolidated\${sym}_M1.parquet"
    if (Test-Path $pf) {
        $ts = Get-Date -Format "HH:mm:ss"
        Write-Host "[$ts]   [OK] $sym M1"
        "  [OK] $sym M1" | Out-File $BOOT_LOG -Append
        $existingParquet += $sym
    } else {
        $ts = Get-Date -Format "HH:mm:ss"
        Write-Host "[$ts]   [WARN] $sym M1 AUSENTE"
        "  [WARN] $sym M1 AUSENTE" | Out-File $BOOT_LOG -Append
        $missingParquet += $sym
    }
}

# step done
Write-Step 'MCP Preflight + Test Battery'
    # MCP Preflight + Test Battery"
    # [OK] MCP Preflight + Test Battery")
& (Join-Path $NC_ROOT "ct_wrapper_preflight.ps1") -VenvPy $VENV_PY -Ctrader $CTRADER -BootLog $BOOT_LOG

Write-Step 'Backfill dados ausentes'
    # Backfill dados ausentes"
    # [OK] Backfill dados ausentes")
# BACKFILL COMPLETO: simbolos sem parquet (first run)
if ($missingParquet.Count -gt 0) {
    $ts = Get-Date -Format "HH:mm:ss"
    Write-Host "[$ts]   [BACKFILL] $($missingParquet.Count) novos simbolos: $($missingParquet -join ', ')"
    foreach ($sym in $missingParquet) {
        Write-Host '  [BACKFILL] Baixando ' + $sym + ' (2 anos)...'
        Write-Host -NoNewline "  ."
        & $VENV_PY "$CTRADER\f0_collector\backfill_orc_coleta.py" '--symbol' $sym 2>&1 | ForEach-Object { Write-Host -NoNewline "." }
        Write-Host ""
        if ($LASTEXITCODE -eq 0) { Write-Host "  [BACKFILL] $sym OK" } else { Write-Host "  [ERRO] Backfill $sym falhou" -ForegroundColor Red }
    }
}

# step done
Write-Step 'GAPS (G23 consolidacao)'
    # GAPS (G23 consolidacao)"
    # [OK] GAPS (G23 consolidacao)")
# GAPS: preenche lacunas do dia anterior (calibracao fresca)
if ($existingParquet.Count -gt 0) {
    $ts = Get-Date -Format "HH:mm:ss"
    Write-Host "[$ts]   [GAPS] Escaneando lacunas + backfill..."
    Write-Host "  ----------------------------------------"
    $ts = Get-Date -Format 'HH:mm:ss'
    Write-Host "[$ts] [GAPS] Scan + backfill em andamento..."
    & $VENV_PY "$CTRADER\gates\run_consolidate_parquet.py" '--check' '--auto-backfill' 2>&1 | ForEach-Object { Write-Host $_ }
    Write-Host "  ----------------------------------------"
    if ($LASTEXITCODE -eq 0) { Write-Host "  [GAPS] Dados atualizados" } else { Write-Host "  [WARN] Gaps parcial - verificar gap_report.json" }
}

# backtest
$btdb = "$CTRADER\status\backtest_trades.db"
if (Test-Path $btdb) { $kb = [math]::Round((Get-Item $btdb).Length/1KB); Write-Host "  [OK] backtest $kb KB"; "  [OK] backtest $kb KB" | Out-File $BOOT_LOG -Append } else { Write-Host "  [WARN] backtest"; "  [WARN] backtest" | Out-File $BOOT_LOG -Append }

# Oxlint (frontend)
try {
    Push-Location "$REACT"
    $oxlintOut = & npx oxlint "src/domains/ctrader/" --quiet 2>&1
    Pop-Location
    if ($LASTEXITCODE -eq 0) { Write-Host "  [OK] Oxlint: 0 errors"; "  [OK] Oxlint" | Out-File $BOOT_LOG -Append } else { Write-Host "  [ERRO] Oxlint: $LASTEXITCODE errors" -ForegroundColor Red; $oxlintOut | Select-Object -First 5 | ForEach-Object { Write-Host "    $_" -ForegroundColor DarkRed }; "  [ERRO] Oxlint FAIL" | Out-File $BOOT_LOG -Append; Read-Host "ENTER para sair"; exit 1 }
} catch { Write-Host "  [WARN] Oxlint: $_"; "  [WARN] Oxlint: $_" | Out-File $BOOT_LOG -Append }

# Ruff
try {
    & $VENV_PY -m ruff check "$CTRADER\utils" "$DASH\routers" 2>&1 | Out-Null
    if ($LASTEXITCODE -eq 0) { Write-Host "  [OK] Ruff: 0 errors"; "  [OK] Ruff" | Out-File $BOOT_LOG -Append } else { Write-Host "  [ERRO] Ruff: $LASTEXITCODE errors" -ForegroundColor Red; "  [ERRO] Ruff FAIL" | Out-File $BOOT_LOG -Append; Read-Host "ENTER para sair"; exit 1 }
} catch { Write-Host "  [WARN] Ruff: $_"; "  [WARN] Ruff: $_" | Out-File $BOOT_LOG -Append }

# step done; Complete-Phase
Start-Phase 'VALIDACAO: Harness + ORQs' 3
Write-Step 'pytest tests/'
    # pytest tests/"
    # [OK] pytest tests/")
# Harness -- suite completa (bloqueante, com progresso por arquivo)
$ts = Get-Date -Format "HH:mm:ss"
Write-Host "[$ts]   [HARNESS] Suite de testes em execucao..."
$harnessFailed = $false
$testLog = Join-Path $env:TEMP "nc_harness.log"
try {
    Push-Location "$CTRADER"
    # Run pytest, capture output to temp file, tail progress
    $proc = Start-Process -FilePath $VENV_PY -ArgumentList "-m","pytest","tests/","-q","--tb=line" -NoNewWindow -PassThru -RedirectStandardOutput $testLog -RedirectStandardError "$testLog.err"
    $lastLine = ""
    while (-not $proc.HasExited) {
        Start-Sleep -Seconds 2
        if (Test-Path $testLog) {
            $lines = Get-Content $testLog -Tail 1 -ErrorAction SilentlyContinue
            if ($lines -and $lines -ne $lastLine) {
                $lastLine = $lines
                # Show test file counts from dots
                if ($lines -match '\.') {
                    Write-Host -NoNewline "`r  [HARNESS] $lines"
                }
            }
        }
    }
    $proc.WaitForExit()
    Write-Host ""
    # Check for failures in output
    if (Test-Path $testLog) {
        $summary = Get-Content $testLog -Raw
        if ($summary -match "FAILED|ERROR") { $harnessFailed = $true }
        $lastLine = ($summary -split "`n" | Select-String "passed|failed" | Select-Object -Last 1)
        if ($lastLine) { Write-Host "  [HARNESS] $lastLine" }
    }
    if (-not $harnessFailed) {
        Remove-Item $testLog, "$testLog.err" -ErrorAction SilentlyContinue
    }
    Pop-Location
} catch { $harnessFailed = $true; Pop-Location -ErrorAction SilentlyContinue }

if ($harnessFailed) {
    $ts = Get-Date -Format "HH:mm:ss"
    Write-Host "[$ts]   [ERRO] Harness: FALHOU" -ForegroundColor Red
    if (Test-Path $testLog) {
        $failures = Get-Content $testLog | Select-String "FAILED|ERROR|AssertionError|TypeError" | Select-Object -First 5
        $failures | ForEach-Object { Write-Host "    $_" -ForegroundColor DarkRed }
    }
    if (-not $failures) { Write-Host "    (verifique o log -- veja /api/ctrader/harness)" }
    "  [ERRO] Harness FAIL" | Out-File $BOOT_LOG -Append
    Read-Host "ENTER para sair"
    exit 1
}
$ts = Get-Date -Format "HH:mm:ss"
Write-Host "[$ts]   [OK] Harness: PASS"; "  [OK] Harness PASS" | Out-File $BOOT_LOG -Append

# step done
Write-Step 'ORQ smoke imports'
    # ORQ smoke imports"
    # [OK] ORQ smoke imports")
# ORQ smoke (bloqueante) -- via gates/orq_smoke.py
Write-Host "  [ORQ] Smoke test..."
$orqFailed = $false
try {
    Push-Location "$CTRADER"
    & $VENV_PY (Join-Path $CTRADER "gates\orq_smoke.py") $CTRADER 2>&1
    if ($LASTEXITCODE -ne 0) { $orqFailed = $true }
    Pop-Location
} catch { $orqFailed = $true; Pop-Location -ErrorAction SilentlyContinue }

if ($orqFailed) {
    $ts = Get-Date -Format "HH:mm:ss"
    Write-Host "[$ts]   [ERRO] ORQ smoke: FALHOU" -ForegroundColor Red
    "  [ERRO] ORQ smoke FAIL" | Out-File $BOOT_LOG -Append
    Read-Host "ENTER para sair"
    exit 1
}
$ts = Get-Date -Format "HH:mm:ss"
Write-Host "[$ts]   [OK] ORQ smoke: PASS"; "  [OK] ORQ smoke PASS" | Out-File $BOOT_LOG -Append

# Cleanup temp files from old approach
$ts = Get-Date -Format "HH:mm:ss"
Write-Host "[$ts]   [OK] ORQ smoke: PASS"; "  [OK] ORQ smoke PASS" | Out-File $BOOT_LOG -Append

"$(Get-Date -Format 'HH:mm:ss') PRE-FLIGHT concluido" | Out-File $BOOT_LOG -Append

    Write-Host "  ----------------------------------------"
Write-Host ""
Write-Host "[PRE-BOOT] Encerrando servicos anteriores..."
"$(Get-Date -Format 'HH:mm:ss') PRE-BOOT iniciado" | Out-File $BOOT_LOG -Append

# 1. PIDs salvos
if (Test-Path $PID_FILE) {
    $killed = 0
    Get-Content $PID_FILE | Where-Object { $_ -match '^\d+$' } | ForEach-Object {
        $id = [int]$_
        if (Get-Process -Id $id -EA SilentlyContinue) {
            Stop-Process -Id $id -Force -EA SilentlyContinue
            $killed++
        }
    }
    Remove-Item $PID_FILE -Force -EA SilentlyContinue
    if ($killed -gt 0) { Write-Host "  [OK] $killed processo(s) encerrado(s)." }
}

# 2. Portas (Get-NetTCPConnection + netstat fallback para non-admin)
#    SEGURANCA: so encerra o dono da porta se for processo DO PROJETO (Test-NCProcess).
#    Processo externo ocupando a porta gera WARN e NAO e encerrado.
foreach ($port in $NC_PORTS) {
    $ownerPids = @()
    # Tenta Get-NetTCPConnection (requer admin)
    try {
        Get-NetTCPConnection -LocalPort $port -EA Stop |
            Select-Object -ExpandProperty OwningProcess -Unique |
            Where-Object { $_ -gt 0 } |
            ForEach-Object { $ownerPids += $_ }
    } catch {}
    # Fallback: netstat (funciona sem admin)
    if ($ownerPids.Count -eq 0) {
        $netstat = netstat -ano 2>$null | Select-String ":$port "
        foreach ($line in $netstat) {
            $parts = $line.ToString().Trim() -split '\s+'
            $pidStr = $parts[-1]
            if ($pidStr -match '^\d+$' -and [int]$pidStr -gt 0) {
                $ownerPids += [int]$pidStr
            }
        }
    }
    foreach ($ownerPid in ($ownerPids | Select-Object -Unique)) {
        if (Test-NCProcess -ProcId $ownerPid) {
            Stop-Process -Id $ownerPid -Force -EA SilentlyContinue
            $ts = Get-Date -Format "HH:mm:ss"
            Write-Host "[$ts]   [OK] Porta $port liberada (PID $ownerPid, processo do projeto)."
        } else {
            $foreign = (Get-Process -Id $ownerPid -EA SilentlyContinue).ProcessName
            if (-not $foreign) { $foreign = "desconhecido" }
            $ts = Get-Date -Format "HH:mm:ss"
            Write-Host "[$ts]   [WARN] Porta $port ocupada por processo externo: ${foreign} (PID ${ownerPid}). Nao sera encerrado."
            "$(Get-Date -Format 'HH:mm:ss') WARN porta $port ocupada por processo externo $foreign PID $ownerPid" | Out-File $BOOT_LOG -Append
        }
    }
}

# 3. Node
$nodeProcs = Get-Process node -EA SilentlyContinue
$killedNode = 0
foreach ($np in $nodeProcs) {
    # SEGURANCA: so encerra node DO PROJETO (react-dashboard).
    # Node de outros apps (Kimi desktop, VS Code, etc.) NUNCA e tocado.
    if (Test-NCProcess -ProcId $np.Id) {
        Stop-Process -Id $np.Id -Force -EA SilentlyContinue
        $killedNode++
    }
}
if ($killedNode -gt 0) { Write-Host "  [OK] $killedNode processo(s) node do projeto encerrado(s)." }

# 4. Python -- SOMENTE a venv exata do projeto ($NC_ROOT\.venv)
#    Nao usa match por CommandLine generico (evita matar processos externos
#    que apenas mencionam o caminho do workspace).
$pyProcs = Get-Process python -EA SilentlyContinue |
    Where-Object { $_.Path -and $_.Path -like "$NC_ROOT\.venv\*" }
if ($pyProcs) {
    $pyProcs | Stop-Process -Force -EA SilentlyContinue
    $ts = Get-Date -Format "HH:mm:ss"
    Write-Host "[$ts]   [OK] $($pyProcs.Count) processo(s) python da venv encerrado(s)."
}

Start-Sleep -Seconds 2
$ts = Get-Date -Format "HH:mm:ss"
Write-Host "[$ts]   [OK] Ambiente limpo."
"$(Get-Date -Format 'HH:mm:ss') PRE-BOOT concluido" | Out-File $BOOT_LOG -Append

    Write-Host "  ----------------------------------------"
$totalSteps = 6

# BOOT 1 -- Ollama
Write-Host "[BOOT 1/$totalSteps] Verificando Ollama..."
try {
    $null = Invoke-WebRequest -Uri 'http://127.0.0.1:11434/api/tags' -TimeoutSec 2 -UseBasicParsing -ErrorAction Stop
    $ts = Get-Date -Format "HH:mm:ss"
    Write-Host "[$ts]   [OK] Ollama ja ativo."
} catch {
    $ts = Get-Date -Format "HH:mm:ss"
    Write-Host "[$ts]   [START] Iniciando Ollama..."
    Start-NC -Title "NC-QWEN" -Dir $NC_ROOT -Command "ollama serve"
    Start-Sleep -Seconds 5
}

# BOOT 2 -- API :7744
Write-Host "[BOOT 2/$totalSteps] Iniciando Dashboard API :7744..."
"$(Get-Date -Format 'HH:mm:ss') BOOT 2 iniciando..." | Out-File $BOOT_LOG -Append
$env:NC_RELOAD = "1"  # hot-reload: ativa uvicorn --reload + reload_dirs
Start-NC -Title "NC-API" -Dir "$NC_ROOT\10.0_ui_dash" `
    -Command "& '$VENV_PY' -X utf8 '$NC_ROOT\10.0_ui_dash\run_api.py'"

# Aguarda API com health check progressivo (ate 60s)
$apiOk = $false
$maxRetries = 10
for ($i = 1; $i -le $maxRetries; $i++) {
    $wait = [Math]::Min(2 + $i * 2, 15)
    Start-Sleep -Seconds $wait
    try {
        $r = Invoke-WebRequest -Uri 'http://127.0.0.1:7744/health' -TimeoutSec 5 -UseBasicParsing -ErrorAction Stop
        $apiOk = $true
        $ts = Get-Date -Format "HH:mm:ss"
        Write-Host "[$ts]   [OK] API :7744 online (tentativa $i, HTTP $($r.StatusCode))."
        "$(Get-Date -Format 'HH:mm:ss') API :7744 ONLINE (tentativa $i)" | Out-File $BOOT_LOG -Append
        break
    } catch {
        Write-Host "  Aguardando API... ($i/$maxRetries, +${wait}s)"
    }
}
if (-not $apiOk) {
    $ts = Get-Date -Format "HH:mm:ss"
    Write-Host "[$ts]   [ERRO] API :7744 NAO SUBIU apos $maxRetries tentativas."
    "$(Get-Date -Format 'HH:mm:ss') API :7744 FALHOU ($maxRetries tentativas)" | Out-File $BOOT_LOG -Append
    # Tenta capturar o erro do Python
    $diag = & $VENV_PY -c "import sys; print(sys.executable); print(sys.path[:5])" 2>&1
    "$(Get-Date -Format 'HH:mm:ss') DIAG: $diag" | Out-File $BOOT_LOG -Append
}

# BOOT 3 -- React :5173
Write-Host "[BOOT 3/$totalSteps] React HUD :5173..."
Start-NC -Title "NC-REACT" -Dir "$NC_ROOT\10.0_ui_dash\react-dashboard" -Command "npm run dev"
Start-Sleep -Seconds 2

# BOOT 4 -- NovaPulse
Write-Host "[BOOT 4/$totalSteps] NovaPulse..."
Start-NC -Title "NC-NOVAPULSE" -Dir "$NC_ROOT\11.0_apps\novapulse\src" `
    -Command "& '$VENV_PY' -X utf8 novapulse.py"
Start-Sleep -Seconds 2

# BOOT 5 -- Tray
Write-Host "[BOOT 5/$totalSteps] Tray Icon..."
Start-NC -Title "NC-TRAY" -Dir $NC_ROOT `
    -Command "& '$VENV_PY' -X utf8 '10.0_ui_dash\NC-10_tray_server.py'"
Start-Sleep -Seconds 2

# BOOT 6 -- F0 Coletor cTrader (unico processo que fala com o MCP; publica status/snapshot.json)
# A9 (INDEX.md/harness.md): harness_boot.py e pre-flight OBRIGATORIO antes do F0 subir.
# Falha bloqueia o F0 (nao o resto do boot) -- import+wiring de 10 orquestradores, sem rede.
Write-Host "[BOOT 6/$totalSteps] F0 Coletor cTrader (fonte unica MCP)..."
Write-Host "  Pre-flight: harness_boot.py (A9)..."
$ctraderDir = "$NC_ROOT\11.0_apps\ctrader"
& $VENV_PY "$ctraderDir\tests\harness_boot.py" *> $null
if ($LASTEXITCODE -eq 0) {
    $ts = Get-Date -Format "HH:mm:ss"
    Write-Host "[$ts]   [OK] harness_boot PASS (10/10 orquestradores) -- iniciando F0."
    Start-NC -Title "NC-CTRADER-F0" -Dir $ctraderDir `
        -Command "& '$VENV_PY' -X utf8 -m f0_collector.orc_coleta --hours 0"
    $ts = Get-Date -Format "HH:mm:ss"
    Write-Host "[$ts]   [START] F0 iniciado (loop continuo, --hours 0 = sem prazo)."
    "$(Get-Date -Format 'HH:mm:ss') F0 iniciado (harness_boot PASS)" | Out-File $BOOT_LOG -Append
} else {
    $ts = Get-Date -Format "HH:mm:ss"
    Write-Host "[$ts]   [ERRO] harness_boot FALHOU -- F0 NAO iniciado (A9: falha bloqueia)."
    Write-Host "         Diagnostico: '$VENV_PY' '$ctraderDir\tests\harness_boot.py'"
    "$(Get-Date -Format 'HH:mm:ss') F0 BLOQUEADO -- harness_boot FALHOU (exit=$LASTEXITCODE)" | Out-File $BOOT_LOG -Append
}
Start-Sleep -Seconds 2

# step done; Complete-Phase
    Write-Host "  ----------------------------------------"
New-Item -Path (Split-Path $PID_FILE) -ItemType Directory -Force -EA SilentlyContinue | Out-Null
$bootPids | Set-Content $PID_FILE
$ts = Get-Date -Format "HH:mm:ss"
Write-Host "[$ts]   [OK] $($bootPids.Count) PIDs salvos."

    Write-Host "  ----------------------------------------"
Write-Host ""
Write-Host "============================================================"
Write-Host " Servicos ativos:"
Write-Host "  Dashboard React  : http://localhost:5173"
Write-Host "  Dashboard API    : http://localhost:7744  ($(if($apiOk){'ONLINE'}else{'FALHOU'}))"
Write-Host "  Ollama/Qwen      : http://localhost:11434"
Write-Host "  Log              : $BOOT_LOG"
Write-Host "============================================================"
Write-Host ""
Write-Host " Pressione ENTER para fechar esta janela..."
Read-Host

Start-Process "http://localhost:5173"

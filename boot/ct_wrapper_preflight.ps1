# CT_WRAPPER_PREFLIGHT.ps1
# Chamado pelo Abrir_NeoCortex_NovaPulse.ps1
# Executa MCP preflight + testes sinteticos antes do backfill
param([string]$VenvPy, [string]$Ctrader, [string]$BootLog)

Write-Host "  [MCP] Preflight + bateria de testes..."
$testResult = & $VenvPy (Join-Path $Ctrader "tests\orchestrator.py") "--skip-real" 2>&1
if ($LASTEXITCODE -eq 0) {
    Write-Host "  [OK] Preflight + sinteticos: PASS"
    "  [OK] Preflight + sinteticos PASS" | Out-File $BootLog -Append
} else {
    Write-Host "  [WARN] Testes falharam - verificar logs"
    Write-Host ($testResult -join "`n")
    "  [WARN] Testes falharam" | Out-File $BootLog -Append
}

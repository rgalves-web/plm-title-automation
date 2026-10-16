$ErrorActionPreference='Stop'
$plmRepo=Split-Path -Parent $PSScriptRoot
Push-Location $plmRepo
try {
    python -X utf8 -c "from src.casefile.db import connect; c=connect(); assert not c.execute('SELECT 1 FROM task_runs WHERE finished_at IS NULL LIMIT 1').fetchone(), 'wait_for_current_execution'; c.close()"
    if ($LASTEXITCODE -ne 0) { throw 'Há execução aberta; preservar a chamada antes de reiniciar.' }
    $plmListeners=Get-NetTCPConnection -LocalPort 8788 -State Listen -ErrorAction SilentlyContinue
    foreach ($plmListener in $plmListeners) {
        $plmProcess=Get-CimInstance Win32_Process -Filter "ProcessId=$($plmListener.OwningProcess)"
        $plmRunner=[regex]::Escape((Join-Path $PSScriptRoot 'run_workbench.py'))
        if ($plmProcess.CommandLine -notmatch 'src\.casefile\.workbench.*serve' -and $plmProcess.CommandLine -notmatch $plmRunner) { throw 'A porta pertence a outro processo; não encerrar.' }
        Stop-Process -Id $plmProcess.ProcessId
    }
    & (Join-Path $PSScriptRoot 'start_workbench.ps1')
} finally { Pop-Location }

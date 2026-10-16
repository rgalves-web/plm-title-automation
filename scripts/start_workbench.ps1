$ErrorActionPreference='Stop'
$plmRepo=Split-Path -Parent $PSScriptRoot
$plmConfig=Join-Path (Split-Path -Parent $plmRepo) 'PLM_OPERACAO\servico\launcher.json'
if (-not (Test-Path -LiteralPath $plmConfig)) { throw 'Prepare a configuração do serviço local primeiro.' }
$plmSettings=Get-Content -LiteralPath $plmConfig -Raw | ConvertFrom-Json
try {
    $plmResponse=Invoke-WebRequest -Uri 'http://127.0.0.1:8788/api/operations' -UseBasicParsing -TimeoutSec 5
    if ($plmResponse.StatusCode -eq 200) { exit 0 }
} catch { }
$plmLogs=Split-Path -Parent $plmConfig
$plmRunner=Join-Path $PSScriptRoot 'run_workbench.py'
Start-Process -FilePath $plmSettings.python -ArgumentList '-X','utf8',('"'+$plmRunner+'"') -WorkingDirectory $plmRepo -WindowStyle Hidden -RedirectStandardOutput (Join-Path $plmLogs 'saida.log') -RedirectStandardError (Join-Path $plmLogs 'erros.log')

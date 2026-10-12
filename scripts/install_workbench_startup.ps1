$ErrorActionPreference='Stop'
$plmLauncher=(Resolve-Path -LiteralPath (Join-Path $PSScriptRoot 'start_workbench.ps1')).Path
$plmEntry='powershell.exe -NoProfile -WindowStyle Hidden -File "'+$plmLauncher+'"'
$plmRunKey='HKCU:\Software\Microsoft\Windows\CurrentVersion\Run'
New-ItemProperty -LiteralPath $plmRunKey -Name 'PLMTitleWorkbench' -Value $plmEntry -PropertyType String -Force | Out-Null
Write-Output 'PLM configurado para iniciar nesta conta ao entrar no Windows.'

param([switch]$Diagnosticar)
$ErrorActionPreference='Stop'
$plmRepo=Split-Path -Parent $PSScriptRoot
Push-Location $plmRepo
try {
    $plmLauncher=Join-Path (Split-Path -Parent $plmRepo) 'PLM_OPERACAO\servico\launcher.json'
    $plmPython=if(Test-Path -LiteralPath $plmLauncher) { (Get-Content -LiteralPath $plmLauncher -Raw | ConvertFrom-Json).python } else { 'python' }
    $plmClaude=& $plmPython -X utf8 -c "from src.infra.terminal import executable; print(executable('A'))"
    if ($LASTEXITCODE -ne 0) { throw 'Instale o Claude Code oficial antes de entrar.' }
    foreach ($plmKey in 'ANTHROPIC_API_KEY','OPENAI_API_KEY','CODEX_API_KEY','ANTHROPIC_AUTH_TOKEN','CLAUDE_CODE_OAUTH_TOKEN') {
        Remove-Item -LiteralPath "Env:$plmKey" -ErrorAction SilentlyContinue
    }
    if($Diagnosticar) { & $plmClaude --version } else { & $plmClaude auth login }
} finally { Pop-Location }

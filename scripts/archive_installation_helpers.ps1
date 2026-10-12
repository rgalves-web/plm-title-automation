$ErrorActionPreference='Stop'
$plmRepo=(Resolve-Path -LiteralPath (Split-Path -Parent $PSScriptRoot)).Path
$plmWorkspace=Split-Path -Parent $plmRepo
$plmArchive=[IO.Path]::GetFullPath((Join-Path $plmWorkspace 'PLM_OPERACAO\historico\implantacao_esteira_2026-10-12\roteiros'))
if (-not $plmArchive.StartsWith([IO.Path]::GetFullPath((Join-Path $plmWorkspace 'PLM_OPERACAO\historico'))+[IO.Path]::DirectorySeparatorChar,[StringComparison]::OrdinalIgnoreCase)) { throw 'Destino fora do histórico declarado.' }
$plmNames=@('configure_operational_roles.py','extract_casefile_infrastructure.py','finalize_workbench_intake.py','record_pilot_provider_block.py','relocate_preserved_controls.ps1','resume_approved_cibola_pilot.py','resume_economic_development.py','resume_pilot_small_batches.py','resume_verified_pilot_round.py','retry_verified_learning.py','apply_paid_learning_result.py','seed_reviewed_learning_correction.py','retry_source_limited_learning.py','prepare_independent_pilot_reviews.py','polish_review_panel.py','record_approved_learning_and_original_reserves.py','seed_bounded_remaining_cases.py','demonstrate_approved_knowledge_use.py','correct_approved_scope_identifier.py')
New-Item -ItemType Directory -Path $plmArchive -Force | Out-Null
$plmRows=@()
foreach ($plmName in $plmNames) {
    $plmOriginal=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot $plmName))
    if (-not $plmOriginal.StartsWith($plmRepo+[IO.Path]::DirectorySeparatorChar,[StringComparison]::OrdinalIgnoreCase)) { throw 'Origem fora do repositório.' }
    if (-not (Test-Path -LiteralPath $plmOriginal)) { continue }
    $plmCopy=Join-Path $plmArchive $plmName
    $plmHash=(Get-FileHash -LiteralPath $plmOriginal -Algorithm SHA256).Hash
    if (Test-Path -LiteralPath $plmCopy) {
        if ((Get-FileHash -LiteralPath $plmCopy -Algorithm SHA256).Hash -ne $plmHash) { throw 'Cópia histórica diferente; preservar ambas antes de retirar.' }
    } else { Copy-Item -LiteralPath $plmOriginal -Destination $plmCopy }
    if ((Get-FileHash -LiteralPath $plmCopy -Algorithm SHA256).Hash -ne $plmHash) { throw 'Preservação não conferida.' }
    $plmRows+=@{original=$plmOriginal;preserved=$plmCopy;sha256=$plmHash;kind='one_time_installation_helper';operation_dependency=$false}
}
$plmRows | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $plmArchive 'manifesto.json') -Encoding UTF8
foreach ($plmRow in $plmRows) { Remove-Item -LiteralPath $plmRow.original }
Write-Output "Roteiros preservados e retirados da operação: $($plmRows.Count)"

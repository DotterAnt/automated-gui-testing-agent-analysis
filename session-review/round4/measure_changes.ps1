param()
$ErrorActionPreference='Stop'
$cliRoot='C:\diplomamunka\potato-cli'
$module=Import-Module (Join-Path $cliRoot 'PoTAToCli\PoTAToCli.psm1') -PassThru
$observations=Get-Content (Join-Path $PSScriptRoot 'observations.json') -Raw | ConvertFrom-Json
$sizes=& $module {
    param($observations)
    $fullBytes=0; $compactBytes=0; $nodes=0
    foreach ($observation in $observations) {
        $compact=[ordered]@{ok=$observation.ok;command='observe';data=@{scope='Working';root=$observation.data.tree.element;
            focusedElement=(ConvertTo-PotatoCompactElement $observation.data.foreground);
            elements=@(ConvertTo-PotatoCompactTree $observation.data.tree);limitReached=$false;
            hint='Selectors are candidates within this scope; check uniqueness. Use click Auto. Add constraints only to disambiguate observed matches.'};
            error=$observation.error;outcome=$observation.outcome;durationMs=$observation.durationMs;explorationCommandId=$observation.explorationCommandId}
        $fullBytes += [Text.Encoding]::UTF8.GetByteCount(($observation | ConvertTo-Json -Depth 80 -Compress))
        $compactBytes += [Text.Encoding]::UTF8.GetByteCount(($compact | ConvertTo-Json -Depth 80 -Compress))
        $nodes += $compact.data.elements.Count
    }
    @{observations=$observations.Count;fullBytes=$fullBytes;compactBytes=$compactBytes;reductionPercent=[Math]::Round(100*(1-$compactBytes/$fullBytes),1);actionableElements=$nodes;
        method='Offline projection of intact observation trees from the supplied log; not a live provider-speed or end-to-end session benchmark.'}
} $observations
$topics=@('start','type','read-pdf','click','press-key','select','observe','wait-element','wait-file','windows')
$watch=[Diagnostics.Stopwatch]::StartNew()
foreach ($topic in $topics) {
    $response=& powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $cliRoot 'potato.ps1') help -Topic $topic | ConvertFrom-Json
    if (-not $response.ok) { throw 'Separate help failed.' }
}
$separate=$watch.ElapsedMilliseconds
$watch.Restart()
$response=& powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $cliRoot 'potato.ps1') help -Topics ($topics -join ',') | ConvertFrom-Json
if (-not $response.ok -or @($response.data.commands.PSObject.Properties).Count -ne 10) { throw 'Combined help failed.' }
$combined=$watch.ElapsedMilliseconds
$result=@{observationProjection=$sizes;help=@{topics=10;separateMs=$separate;combinedMs=$combined;method='One local sample, ten separate powershell.exe help processes versus one combined help process. No desktop actions.'}}
$result | ConvertTo-Json -Depth 8 | Set-Content (Join-Path $PSScriptRoot 'measurements.json') -Encoding UTF8
$result | ConvertTo-Json -Depth 8

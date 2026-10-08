param()
$ErrorActionPreference='Stop'
$workspace='C:\diplomamunka'
$python='C:\Users\DottedAnt\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
$tests=@(
    @{path='potato-cli\tests\Regression.Tests.ps1';args=@()},
    @{path='potato-cli\tests\Interaction.Tests.ps1';args=@()},
    @{path='potato-cli\tests\Focus.Tests.ps1';args=@()},
    @{path='potato-cli\tests\Lifecycle.Tests.ps1';args=@()},
    @{path='potato-cli\tests\Provider.Tests.ps1';args=@()},
    @{path='potato-cli\tests\Discovery.Tests.ps1';args=@()},
    @{path='potato-cli\tests\PathInput.Tests.ps1';args=@()},
    @{path='potato-cli\tests\AuthoringExperience.Tests.ps1';args=@()},
    @{path='potato-cli\tests\Dpi.Tests.ps1';args=@()},
    @{path='potato-cli\tests\Drag.Tests.ps1';args=@()},
    @{path='potato-cli\tests\Pdf.Tests.ps1';args=@()},
    @{path='potato-cli\tests\Pdf.External.Tests.ps1';args=@('-PythonPath',$python)},
    @{path='automated-gui-testing-agent-framework\tests\Runtime.Regression.Tests.ps1';args=@()},
    @{path='automated-gui-testing-agent-framework\tests\Authoring.Regression.Tests.ps1';args=@()},
    @{path='potato-cli\tests\Gui.Smoke.Tests.ps1';args=@()},
    @{path='potato-cli\tests\Gui.Lifecycle.Tests.ps1';args=@()}
)
$results=@()
foreach ($test in $tests) {
    $watch=[Diagnostics.Stopwatch]::StartNew()
    $arguments=@('-NoProfile','-ExecutionPolicy','Bypass','-File',(Join-Path $workspace $test.path))+$test.args
    $ErrorActionPreference='Continue'
    $output=& powershell.exe @arguments 2>&1
    $code=$LASTEXITCODE
    $ErrorActionPreference='Stop'
    $results+=@{test=$test.path;exitCode=$code;elapsedMs=$watch.ElapsedMilliseconds;output=($output -join "`n")}
    $output | ForEach-Object {Write-Output $_}
    if ($code -ne 0) {break}
}
$ok=$results.Count -eq $tests.Count -and @($results | Where-Object {$_.exitCode -ne 0}).Count -eq 0
@{ok=$ok;timestamp=(Get-Date).ToString('o');tests=$results} | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $PSScriptRoot 'verification.json') -Encoding UTF8
if (-not $ok) {exit 1}



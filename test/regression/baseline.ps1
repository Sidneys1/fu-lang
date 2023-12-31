$Whitelist = $Args;

$ROOT = Resolve-Path $PSScriptRoot\..\..;
Write-Host -ForegroundColor DarkGray "Repository root is ``$ROOT``.";

$PYTHON = (get-command python).Source;

if (-not $PYTHON.StartsWith($ROOT)) {
    Write-Host -ForegroundColor Red "Forgot to source the venv?"
    exit 1;
}

Write-Host -ForegroundColor DarkGray "Using Python at ``$PYTHON``."

Push-Location $ROOT;
ls -Filter '*.fu' $PSScriptRoot `
| ? { ($Whitelist.Count -eq 0) -or ($_.BaseName -in $Whitelist) -or ($_.Name -in $Whitelist) } `
| % {
    $output = "$PSScriptRoot\output\" + $_.Name
    & cmd.exe /c "python -m fu.compiler `"$_`" 2>`"$output.stderr`" >`"$output.stdout`"";
    Write-Host "[✓] Baselined ``$($_.BaseName)``"
}
Pop-Location;
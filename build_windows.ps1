$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ProjectRoot

$PythonPath = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $PythonPath)) {
    $PythonPath = (Get-Command python -ErrorAction Stop).Source
}
& $PythonPath -m pip install -e ".[build]"
if ($LASTEXITCODE -ne 0) { throw "Dependency installation failed." }
& $PythonPath -m PyInstaller --noconfirm --clean --windowed --name FrameForge run_frameforge.py
if ($LASTEXITCODE -ne 0) { throw "PyInstaller build failed." }

$Version = (Get-Content VERSION -Raw).Trim()
$Bundle = Join-Path $ProjectRoot "dist\FrameForge"
Copy-Item README.md, LICENSE -Destination $Bundle
$Archive = Join-Path $ProjectRoot "dist\FrameForge-$Version-windows-x64.zip"
if (Test-Path $Archive) { Remove-Item -LiteralPath $Archive -Force }
Compress-Archive -Path $Bundle -DestinationPath $Archive -CompressionLevel Optimal
$Hash = (Get-FileHash -LiteralPath $Archive -Algorithm SHA256).Hash.ToLowerInvariant()
Set-Content -LiteralPath "$Archive.sha256" -Value "$Hash  $(Split-Path -Leaf $Archive)" -Encoding ascii
Write-Output "Created $Archive"
Write-Output "SHA-256 $Hash"

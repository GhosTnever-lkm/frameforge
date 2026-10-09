param([string]$PythonPath)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ProjectRoot

$PythonPath = if ($PythonPath) {
    (Resolve-Path -LiteralPath $PythonPath).Path
} else {
    Join-Path $ProjectRoot ".venv\Scripts\python.exe"
}
if (-not (Test-Path -LiteralPath $PythonPath)) {
    $PythonPath = (Get-Command python -ErrorAction Stop).Source
}
& $PythonPath -m pip install -e ".[build]"
if ($LASTEXITCODE -ne 0) { throw "Dependency installation failed." }
$OriginalPath = $env:PATH
try {
    # Some bundled developer runtimes put an incompatible ICU DLL in PATH.
    # Qt resolves ICU by the generic name `icuuc.dll`, so keep the build
    # isolated from Poppler's renamed/versioned ICU exports.
    $env:PATH = ($OriginalPath -split ';' | Where-Object {
        $_ -notmatch '\\poppler\\Library\\bin$'
    }) -join ';'
    & $PythonPath -m PyInstaller --noconfirm --clean --windowed --name FrameForge run_frameforge.py
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller build failed." }
}
finally {
    $env:PATH = $OriginalPath
}

$Version = (Get-Content VERSION -Raw).Trim()
$Bundle = Join-Path $ProjectRoot "dist\FrameForge"
$SitePackages = (& $PythonPath -c "import sysconfig; print(sysconfig.get_paths()['purelib'])").Trim()
if ($LASTEXITCODE -ne 0 -or -not $SitePackages) { throw "Could not locate the active Python site-packages directory." }
$QtPluginSource = Join-Path $SitePackages "PySide6\plugins"
$QtPluginTarget = Join-Path $Bundle "_internal\PySide6\plugins"
if (-not (Test-Path -LiteralPath (Join-Path $QtPluginSource "platforms\qwindows.dll"))) {
    throw "The PySide6 Windows platform plugin was not found."
}
New-Item -ItemType Directory -Path $QtPluginTarget -Force | Out-Null
Copy-Item -Path (Join-Path $QtPluginSource "*") -Destination $QtPluginTarget -Recurse -Force
Copy-Item README.md, LICENSE -Destination $Bundle
$Archive = Join-Path $ProjectRoot "dist\FrameForge-$Version-windows-x64.zip"
if (Test-Path $Archive) { Remove-Item -LiteralPath $Archive -Force }
Compress-Archive -Path $Bundle -DestinationPath $Archive -CompressionLevel Optimal
$Hash = (Get-FileHash -LiteralPath $Archive -Algorithm SHA256).Hash.ToLowerInvariant()
Set-Content -LiteralPath "$Archive.sha256" -Value "$Hash  $(Split-Path -Leaf $Archive)" -Encoding ascii
Write-Output "Created $Archive"
Write-Output "SHA-256 $Hash"

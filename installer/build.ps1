# Builds the Sunshine Windows installer end-to-end: PyInstaller freeze
# + Inno Setup compile. Run from the repo root:
#   .\installer\build.ps1
#
# Requirements (not installed by this script):
#   - pip install pyinstaller   (inside venv)
#   - Inno Setup 6 installed, with ISCC.exe on PATH or at the default
#     location checked below (https://jrsoftware.org/isdl.php)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot

Write-Host "== 1/2: PyInstaller freeze ==" -ForegroundColor Cyan
& "$repoRoot\venv\Scripts\python.exe" -m PyInstaller "installer\sunshine.spec" --noconfirm
if ($LASTEXITCODE -ne 0) { throw "PyInstaller build failed (exit $LASTEXITCODE)" }

Write-Host "== 2/2: Inno Setup compile ==" -ForegroundColor Cyan
$iscc = Get-Command "ISCC.exe" -ErrorAction SilentlyContinue
if (-not $iscc) {
    $defaultPath = "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe"
    if (Test-Path $defaultPath) {
        $iscc = $defaultPath
    } else {
        throw "ISCC.exe (Inno Setup Compiler) not found on PATH or at the default install location. Install Inno Setup 6 from https://jrsoftware.org/isdl.php first."
    }
} else {
    $iscc = $iscc.Source
}

& $iscc "installer\setup.iss"
if ($LASTEXITCODE -ne 0) { throw "Inno Setup compile failed (exit $LASTEXITCODE)" }

Write-Host "Done. Installer at installer\dist_installer\SunshineSetup.exe" -ForegroundColor Green

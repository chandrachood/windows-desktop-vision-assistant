param(
    [switch]$Windowed,
    [switch]$NoClean
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $projectRoot

function Get-PythonExecutable {
    $venvPython = Join-Path $projectRoot "venv\Scripts\python.exe"
    if (Test-Path $venvPython) {
        return $venvPython
    }
    return "python"
}

$pythonExe = Get-PythonExecutable

Write-Host "Using Python: $pythonExe"
& $pythonExe -m pip install --upgrade pyinstaller

if (-not $NoClean) {
    if (Test-Path "build") { Remove-Item "build" -Recurse -Force }
    if (Test-Path "dist") { Remove-Item "dist" -Recurse -Force }
    if (Test-Path "VisionAssistanceApp.spec") { Remove-Item "VisionAssistanceApp.spec" -Force }
}

$args = @(
    "-m", "PyInstaller",
    "--noconfirm",
    "--clean",
    "--onefile",
    "--name", "VisionAssistanceApp",
    "--collect-all", "google.genai",
    "--collect-all", "pyautogui",
    "--collect-all", "pyttsx3",
    "--collect-all", "cryptography",
    "--hidden-import", "pyttsx3.drivers",
    "--hidden-import", "pyttsx3.drivers.sapi5",
    "--add-data", "config.example.json;."
)

if ($Windowed) {
    $args += "--noconsole"
} else {
    $args += "--console"
}

$args += "main.py"

Write-Host "Building executable..."
& $pythonExe @args

Copy-Item "config.example.json" "dist\config.example.json" -Force

Write-Host ""
Write-Host "Build complete."
Write-Host "Executable: dist\VisionAssistanceApp.exe"
Write-Host "Config template: dist\config.example.json"
Write-Host ""
Write-Host "Runtime files for the EXE are stored in:"
Write-Host "$env:APPDATA\VisionAssistanceApp"

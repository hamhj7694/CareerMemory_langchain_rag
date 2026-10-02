$ErrorActionPreference = "Stop"
$projectRoot = $PSScriptRoot
$python = Join-Path $projectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $python)) {
    throw "Python virtual environment missing: $python"
}

# cmd pushd maps a UNC share to a temporary drive letter for npm.
$frontendCommand = 'pushd "' + $projectRoot + '" && set VITE_USE_MOCK=false&& set VITE_API_BASE_URL=same-origin&& npm run build'
cmd.exe /d /c $frontendCommand
if ($LASTEXITCODE -ne 0) { throw "Frontend build failed" }

$workPath = Join-Path $env:TEMP "CareerMemoryPyInstaller"
$distPath = Join-Path $projectRoot "release"
$sourcePath = Join-Path $projectRoot "career_memory_launcher.py"
$webData = (Join-Path $projectRoot "dist") + ";web"
$installerArgs = @(
    "--clean", "--noconfirm", "--onedir",
    "--name", "CareerMemory",
    "--distpath", $distPath,
    "--workpath", $workPath,
    "--specpath", $projectRoot,
    "--paths", $projectRoot,
    "--add-data", $webData,
    "--collect-all", "chromadb",
    "--collect-all", "tiktoken",
    "--collect-all", "langchain_google_genai",
    "--collect-all", "langchain_chroma",
    $sourcePath
)

Push-Location $env:USERPROFILE
try {
    & $python -m PyInstaller @installerArgs
    if ($LASTEXITCODE -ne 0) { throw "Windows executable build failed" }
}
finally {
    Pop-Location
}

Copy-Item -LiteralPath (Join-Path $projectRoot ".env.example") -Destination (Join-Path $distPath "CareerMemory\.env.example") -Force
Write-Host "Created: $(Join-Path $distPath 'CareerMemory\CareerMemory.exe')"
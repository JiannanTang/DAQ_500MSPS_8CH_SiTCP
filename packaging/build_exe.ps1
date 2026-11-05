param(
    [switch]$SkipInstall,
    [switch]$SkipZip
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$venvRoot = Join-Path $projectRoot ".packaging-venv"
$venvPython = Join-Path $venvRoot "Scripts\python.exe"

if (-not (Test-Path -LiteralPath $venvPython)) {
    python -m venv $venvRoot
}

if (-not $SkipInstall) {
    & $venvPython -m pip install --disable-pip-version-check --no-deps --only-binary=:all: -r (Join-Path $PSScriptRoot "requirements-build.txt")
}

& $venvPython -c "import PyInstaller"
if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller is not available. Run without -SkipInstall."
}

Push-Location $projectRoot
try {
    $previousBuildPath = $env:PATH
    $env:PATH = "$env:SystemRoot\System32;$env:SystemRoot"
    try {
        & $venvPython -m PyInstaller --noconfirm --clean (Join-Path $PSScriptRoot "DAQ_500MSPS_8CH_SiTCP.spec")
    }
    finally {
        $env:PATH = $previousBuildPath
    }
    if ($LASTEXITCODE -ne 0) {
        throw "PyInstaller build failed with exit code $LASTEXITCODE"
    }

    $productName = "DAQ_500MSPS_8CH_SiTCP"
    $distRoot = Join-Path $projectRoot ("dist\" + $productName)
    $distConfig = Join-Path $distRoot "config"
    New-Item -ItemType Directory -Force -Path $distConfig | Out-Null
    Copy-Item -LiteralPath (Join-Path $projectRoot "config\registers.toml") -Destination (Join-Path $distConfig "registers.toml") -Force
    Copy-Item -LiteralPath (Join-Path $PSScriptRoot "README_DIST.txt") -Destination (Join-Path $distRoot "README.txt") -Force
    Copy-Item -LiteralPath (Join-Path $PSScriptRoot "THIRD_PARTY_NOTICES.txt") -Destination (Join-Path $distRoot "THIRD_PARTY_NOTICES.txt") -Force
    New-Item -ItemType Directory -Force -Path (Join-Path $distRoot "captures") | Out-Null

    $previousQtPlatform = $env:QT_QPA_PLATFORM
    try {
        $env:QT_QPA_PLATFORM = "offscreen"
        $smokeProcess = Start-Process -FilePath (Join-Path $distRoot ($productName + ".exe")) -ArgumentList "--smoke-test" -WorkingDirectory $distRoot -WindowStyle Hidden -PassThru
        if (-not $smokeProcess.WaitForExit(15000)) {
            Stop-Process -Id $smokeProcess.Id -Force -ErrorAction SilentlyContinue
            throw "Packaged application smoke test timed out."
        }
        if ($smokeProcess.ExitCode -ne 0) {
            throw "Packaged application smoke test failed with exit code $($smokeProcess.ExitCode)"
        }
    }
    finally {
        if ($null -eq $previousQtPlatform) {
            Remove-Item Env:QT_QPA_PLATFORM -ErrorAction SilentlyContinue
        }
        else {
            $env:QT_QPA_PLATFORM = $previousQtPlatform
        }
    }

    $sitePackages = (& $venvPython -c "import site; print(site.getsitepackages()[-1])").Trim()
    $licenseDest = Join-Path $distRoot "LICENSES"
    New-Item -ItemType Directory -Force -Path $licenseDest | Out-Null
    foreach ($distInfo in Get-ChildItem -LiteralPath $sitePackages -Directory -Filter "*dist-info") {
        if ($distInfo.Name -notmatch "^(PySide6|pyside6|shiboken6|numpy|pyinstaller)") {
            continue
        }
        $licenses = Join-Path $distInfo.FullName "licenses"
        if (Test-Path -LiteralPath $licenses) {
            $licenseTarget = Join-Path $licenseDest $distInfo.Name
            New-Item -ItemType Directory -Force -Path $licenseTarget | Out-Null
            Copy-Item -Path (Join-Path $licenses "*") -Destination $licenseTarget -Recurse -Force
        }
    }

    if (-not $SkipZip) {
        $versionLine = Select-String -LiteralPath (Join-Path $projectRoot "pyproject.toml") -Pattern '^version = "([^"]+)"' | Select-Object -First 1
        $version = if ($versionLine) { $versionLine.Matches[0].Groups[1].Value } else { "dev" }
        $zipPath = Join-Path $projectRoot ("dist\" + $productName + "-" + $version + "-win64.zip")
        if (Test-Path -LiteralPath $zipPath) {
            Remove-Item -LiteralPath $zipPath -Force
        }
        Compress-Archive -Path (Join-Path $distRoot "*") -DestinationPath $zipPath
        Write-Host "Created: $zipPath"
    }

    Write-Host "Created: $distRoot"
}
finally {
    Pop-Location
}


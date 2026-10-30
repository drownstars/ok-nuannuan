$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$frameworkUrl = 'https://github.com/ok-oldking/ok-script.git'
$frameworkCommit = '2424dc7da0c4a16e716fade8377b69871229c479'
if (-not (Test-Path -LiteralPath 'ok-script/ok/__init__.py')) {
    if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
        throw 'Git is required to restore ok-script. Install Git for Windows, then run bootstrap.ps1 again.'
    }
    if ((Test-Path -LiteralPath '.git') -and (Test-Path -LiteralPath '.gitmodules')) {
        & git submodule update --init -- ok-script
        if ($LASTEXITCODE -ne 0) { throw 'Framework submodule initialization failed.' }
    } else {
        & git clone --no-checkout $frameworkUrl ok-script
        if ($LASTEXITCODE -ne 0) { throw 'Framework download failed.' }
        & git -C ok-script checkout --detach $frameworkCommit
        if ($LASTEXITCODE -ne 0) { throw 'Cannot restore the pinned framework revision.' }
    }
}
if (-not (Test-Path -LiteralPath 'ok-script/ok/__init__.py')) {
    throw 'Framework source is missing; check the ok-script submodule before installing.'
}
New-Item -ItemType Directory -Force .cache\tmp | Out-Null
$env:TEMP = Join-Path $PSScriptRoot '.cache\tmp'
$env:TMP = $env:TEMP
$env:OK_SCRIPT_BUILD_VERSION = '2.0.17+nuannuan.2424dc7'
if (-not (Test-Path .venv\Scripts\python.exe)) {
    py -3.12 -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw 'Python 3.12 environment creation failed.' }
}
$projectPy = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
& $projectPy -m ensurepip --upgrade
if ($LASTEXITCODE -ne 0) { throw 'pip bootstrap failed.' }
& $projectPy -m pip install --index-url https://pypi.org/simple --cache-dir .cache\pip -r requirements-dev.txt
if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed.' }
if (Test-Path -LiteralPath 'whimbox_app/python-embedded/Lib/site-packages/whimbox/assets') {
    & $projectPy tools\import_assets.py
    if ($LASTEXITCODE -ne 0) { throw 'Asset import failed.' }
    & $projectPy tools\import_routes.py
    if ($LASTEXITCODE -ne 0) { throw 'Route import failed.' }
} elseif (-not (Test-Path -LiteralPath 'assets/manifest.json') -or -not (Test-Path -LiteralPath 'routes/manifest.json')) {
    throw 'Bundled assets or routes are missing. Restore the supplied assets before reinstalling.'
} else {
    Write-Host 'Using the bundled assets and route library; the original Whimbox folder is not required.'
}
& $projectPy -m pip check
if ($LASTEXITCODE -ne 0) { throw 'Dependency verification failed.' }
Write-Host 'Ready. Double-click the VBS launcher or run .venv\Scripts\pythonw.exe start_gui.py.'

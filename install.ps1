<#
8Bit Music Code Studio installer for Windows (PowerShell 5.1+ or 7+). Puts `8bms` on your PATH.

  irm https://raw.githubusercontent.com/RechargedIdeas/8bit-music-code-studio/main/install.ps1 | iex

With options (extras, uninstall...), either set env vars before the one-liner:
  $env:EIGHTBMS_EXTRAS = "all"; irm .../install.ps1 | iex          # all | audio,midi,mcp,acp,ml
  $env:EIGHTBMS_UNINSTALL = "1"; irm .../install.ps1 | iex
  $env:EIGHTBMS_METHOD = "venv"; irm .../install.ps1 | iex          # force pipx | uv | venv
or download and run it:
  irm .../install.ps1 -OutFile install.ps1; .\install.ps1 -All
  .\install.ps1 -Uninstall [-Purge]

Options: -All -Audio -Midi -Mcp -Acp -Ml, -Method auto|pipx|uv|venv, -Source <folder|url>,
         -Python <path>, -NoModifyPath, -Uninstall, -Purge
Re-running upgrades in place. Never needs admin rights.
#>
param(
    [switch]$All, [switch]$Audio, [switch]$Midi, [switch]$Mcp, [switch]$Acp, [switch]$Ml,
    [ValidateSet("auto", "pipx", "uv", "venv")][string]$Method = "auto",
    [string]$Source = "",
    [string]$Python = "",
    [switch]$NoModifyPath,
    [switch]$Uninstall,
    [switch]$Purge
)

function Install-8bms {
    param($Opt)
    $ErrorActionPreference = "Stop"
    $Pkg = "eightbit-music-code-studio"
    $Repo = "https://github.com/RechargedIdeas/8bit-music-code-studio"
    $HomeDir = if ($env:EIGHTBMS_HOME) { $env:EIGHTBMS_HOME } else { Join-Path $HOME ".8bms" }
    $Venv = Join-Path $HomeDir "venv"
    $BinDir = Join-Path $HomeDir "bin"
    $OnWindows = ($PSVersionTable.PSEdition -eq "Desktop") -or $IsWindows
    $VenvExe = if ($OnWindows) { Join-Path $Venv "Scripts\8bms.exe" } else { Join-Path $Venv "bin/8bms" }
    $VenvPy = if ($OnWindows) { Join-Path $Venv "Scripts\python.exe" } else { Join-Path $Venv "bin/python" }

    function Say($m) { Write-Host "==> $m" -ForegroundColor Cyan }
    function Ok($m) { Write-Host " ok $m" -ForegroundColor Green }
    function Warn($m) { Write-Host "warn $m" -ForegroundColor Yellow }
    function Have($c) { [bool](Get-Command $c -ErrorAction SilentlyContinue) }
    function Run([string]$exe, [string[]]$a) {
        & $exe @a | Out-Host
        return ($LASTEXITCODE -eq 0)
    }

    # extras from switches or $env:EIGHTBMS_EXTRAS
    $extras = New-Object System.Collections.Generic.List[string]
    foreach ($n in "all", "audio", "midi", "mcp", "acp", "ml") { if ($Opt[$n]) { $extras.Add($n) } }
    if ($env:EIGHTBMS_EXTRAS) { foreach ($e in ($env:EIGHTBMS_EXTRAS -split "[,\s]+")) { if ($e -and -not $extras.Contains($e)) { $extras.Add($e) } } }
    $src = if ($Opt.Source) { $Opt.Source } elseif ($env:EIGHTBMS_SOURCE) { $env:EIGHTBMS_SOURCE } else { "$Repo/archive/refs/heads/main.zip" }
    if (Test-Path $src) { $src = "file:///" + (((Resolve-Path $src).Path -replace "\\", "/").TrimStart("/")) }
    elseif ($src -match "^https://github\.com/.+\.git$") { $src = "git+$src" }
    function Spec { if ($extras.Count) { "$Pkg[$($extras -join ',')] @ $src" } else { "$Pkg @ $src" } }

    if ($Opt.Uninstall -or $env:EIGHTBMS_UNINSTALL -eq "1") {
        Say "Uninstalling 8bms"
        $removed = $false
        if ((Have pipx) -and ((pipx list --short 2>$null) -match "^$Pkg ")) { pipx uninstall $Pkg | Out-Host; $removed = $true }
        if ((Have uv) -and ((uv tool list 2>$null) -match "^$Pkg ")) { uv tool uninstall $Pkg | Out-Host; $removed = $true }
        if (Test-Path $Venv) { Remove-Item -Recurse -Force $Venv; $removed = $true }
        foreach ($f in "8bms.cmd", "8bms") { $p = Join-Path $BinDir $f; if (Test-Path $p) { Remove-Item -Force $p } }
        if ($OnWindows) {
            $userPath = [Environment]::GetEnvironmentVariable("Path", "User")
            if ($userPath -and ($userPath -split ";") -contains $BinDir) {
                [Environment]::SetEnvironmentVariable("Path", (($userPath -split ";") | Where-Object { $_ -and $_ -ne $BinDir }) -join ";", "User")
            }
        }
        if (($Opt.Purge -or $env:EIGHTBMS_PURGE -eq "1") -and (Test-Path $HomeDir)) { Remove-Item -Recurse -Force $HomeDir; Ok "deleted $HomeDir" }
        elseif (Test-Path $HomeDir) { Write-Host "   your songs/handles/plugins in $HomeDir were kept (add -Purge to delete)" }
        if ($removed) { Ok "8bms removed" } else { Warn "nothing to remove (8bms was not installed by this script)" }
        return $true
    }

    Say "8Bit Music Code Studio installer (PowerShell $($PSVersionTable.PSVersion))"

    # find Python 3.10+ (prefer one with tkinter for the GUI)
    $check = "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)"
    $py = $null; $pyArgs = @()
    $cands = @()
    if ($Opt.Python) { $cands += , @($Opt.Python) }
    if (Have py) { foreach ($v in "3.13", "3.12", "3.11", "3.10") { $cands += , @("py", "-$v") } }
    foreach ($c in "python", "python3") { if (Have $c) { $cands += , @($c) } }
    foreach ($pass in 1, 2) {
        foreach ($c in $cands) {
            $exe = $c[0]; $a = @($c | Select-Object -Skip 1)
            $code = if ($pass -eq 1) { "$check; import tkinter" } else { $check }
            try { & $exe @a -c $code 2>$null | Out-Null } catch { continue }
            if ($LASTEXITCODE -eq 0) { $py = $exe; $pyArgs = $a; break }
        }
        if ($py) { break }
    }
    $pyPath = $null
    if ($py) {
        $pyPath = (& $py @pyArgs -c "import sys; print(sys.executable)").Trim()
        $ver = (& $pyPath -c "import platform; print(platform.python_version())").Trim()
        Ok "Python $ver at $pyPath"
    } elseif ((Have uv) -and $Opt.Method -ne "venv") {
        Warn "no Python 3.10+ found; uv will download one"
    } else {
        Write-Host "Python 3.10+ is required. Install it, then re-run:" -ForegroundColor Red
        Write-Host "  winget install -e --id Python.Python.3.12      (or https://www.python.org/downloads/ - tick 'Add python.exe to PATH')"
        Write-Host "  or: winget install -e --id astral-sh.uv   (uv can fetch Python for you)"
        return $false
    }

    $m = $Opt.Method
    if ($env:EIGHTBMS_METHOD -and $m -eq "auto") { $m = $env:EIGHTBMS_METHOD }
    # a tool counts as usable only if it actually runs (a pipx/uv shim left behind by an
    # uninstalled Python fails with "The system cannot find the path specified")
    function Works([string]$c) {
        if (-not (Have $c)) { return $false }
        try { & $c --version 2>$null | Out-Null; return ($LASTEXITCODE -eq 0) } catch { return $false }
    }
    $methods = @()
    if ($m -eq "auto") {
        if ((Works pipx) -and $pyPath) { $methods += "pipx" } elseif ((Have pipx) -and $pyPath) { Warn "pipx is on PATH but does not run; skipping it" }
        if (Works uv) { $methods += "uv" } elseif (Have uv) { Warn "uv is on PATH but does not run; skipping it" }
        if ($pyPath) { $methods += "venv" }
    } else { $methods = @($m) }

    $script:exe8 = $null
    function TryInstall([string]$spec) {
        switch ($m) {
            "pipx" {
                if (-not (Run "pipx" @("install", "--force", "--python", $pyPath, $spec))) { return $false }
                $d = (pipx environment --value PIPX_BIN_DIR 2>$null)
                if (-not $d) { $d = Join-Path $HOME ".local\bin" }
                $script:exe8 = Join-Path $d.Trim() ($(if ($OnWindows) { "8bms.exe" } else { "8bms" }))
            }
            "uv" {
                $p = if ($pyPath) { $pyPath } else { "3.12" }
                if (-not (Run "uv" @("tool", "install", "--force", "--reinstall", "--python", $p, $spec))) { return $false }
                $d = (uv tool dir --bin 2>$null)
                if (-not $d) { $d = Join-Path $HOME ".local\bin" }
                $script:exe8 = Join-Path $d.Trim() ($(if ($OnWindows) { "8bms.exe" } else { "8bms" }))
            }
            "venv" {
                if (-not $pyPath) { Write-Host "error the venv method needs Python 3.10+" -ForegroundColor Red; return $false }
                New-Item -ItemType Directory -Force -Path $HomeDir | Out-Null
                if (-not (Test-Path $VenvPy)) {
                    if (-not (Run $pyPath @("-m", "venv", $Venv))) { Write-Host "error could not create a virtualenv at $Venv" -ForegroundColor Red; return $false }
                }
                if (-not (Run $VenvPy @("-m", "pip", "install", "-q", "--disable-pip-version-check", "--upgrade", "pip"))) { return $false }
                if (-not (Run $VenvPy @("-m", "pip", "install", "-q", "--disable-pip-version-check", "--upgrade", $spec))) { return $false }
                if (-not (Run $VenvPy @("-m", "pip", "install", "-q", "--disable-pip-version-check", "--force-reinstall", "--no-deps", $spec))) { return $false }
                New-Item -ItemType Directory -Force -Path $BinDir | Out-Null
                if ($OnWindows) {
                    $shim = Join-Path $BinDir "8bms.cmd"
                    Set-Content -Path $shim -Encoding ASCII -Value "@echo off`r`n`"$VenvExe`" %*"
                    $script:exe8 = $shim
                } else {
                    $shim = Join-Path $BinDir "8bms"
                    if (Test-Path $shim) { Remove-Item -Force $shim }
                    New-Item -ItemType SymbolicLink -Path $shim -Target $VenvExe | Out-Null
                    $script:exe8 = $shim
                }
            }
        }
        return $true
    }

    $installed = $false
    foreach ($candidate in $methods) {
        $m = $candidate
        $spec = Spec
        Say "Installing with ${m}: $spec"
        $okNow = $false
        try { $okNow = TryInstall $spec } catch { Warn "$m failed: $($_.Exception.Message)" }
        if (-not $okNow -and $extras.Count) {
            Warn "extras [$($extras -join ',')] failed to install (often: no prebuilt wheel for this Python, e.g. python-rtmidi)."
            Warn "installing the core app without them; re-run with the flag later to add them."
            $extras.Clear(); $spec = Spec
            try { $okNow = TryInstall $spec } catch { Warn "$m failed: $($_.Exception.Message)" }
        }
        if ($okNow) { $installed = $true; break }
        Warn "install with $m failed; trying the next method"
    }
    if (-not $installed) { Write-Host "error install failed (see the messages above). Try: `$env:EIGHTBMS_METHOD = 'venv'; irm .../install.ps1 | iex" -ForegroundColor Red; return $false }

    $exe8 = $script:exe8
    if (-not ($exe8 -and (Test-Path $exe8))) { $g = Get-Command 8bms -ErrorAction SilentlyContinue; if ($g) { $exe8 = $g.Source } }
    if (-not ($exe8 -and (Test-Path $exe8))) { Write-Host "error install finished but the 8bms command was not found" -ForegroundColor Red; return $false }
    $ver = (& $exe8 --version 2>&1 | Out-String).Trim()
    if ($LASTEXITCODE -ne 0) { Write-Host "error 8bms was installed but does not run: $ver" -ForegroundColor Red; return $false }
    Ok "$ver -> $exe8"

    # PATH: user-level, no admin
    $dir = Split-Path -Parent $exe8
    $sep = [IO.Path]::PathSeparator
    if (-not (($env:Path -split $sep) -contains $dir)) {
        $env:Path = "$dir$sep$env:Path"     # this session
        if ($OnWindows -and -not $Opt.NoModifyPath) {
            $userPath = [Environment]::GetEnvironmentVariable("Path", "User")
            if (-not (($userPath -split ";") -contains $dir)) {
                [Environment]::SetEnvironmentVariable("Path", (@($dir) + @($userPath -split ";" | Where-Object { $_ })) -join ";", "User")
            }
            Warn "added $dir to your user PATH; open a new terminal for other windows to see it"
        } else {
            Warn "$dir is not on PATH; add it to your profile"
        }
    } else { Ok "$dir is on PATH" }

    $tkPy = if ($m -eq "venv") { $VenvPy } else { $pyPath }
    if ($tkPy) {
        & $tkPy -c "import tkinter" 2>$null | Out-Null
        if ($LASTEXITCODE -ne 0) { Warn "tkinter is missing, so the GUI won't open (CLI/MCP/ACP/HTTP work). Reinstall Python from python.org with 'tcl/tk and IDLE' ticked." }
    }
    if (-not (Have ffmpeg)) { Write-Host "   tip: winget install -e --id Gyan.FFmpeg  for OGG/MP3/FLAC export (WAV always works)" }

    Write-Host ""
    Write-Host "Done. Try:" -ForegroundColor Green
    Write-Host "  8bms                      # open the GUI"
    Write-Host "  8bms studio               # terminal studio"
    Write-Host "  8bms compose `"mellow space loop`" --bars 8 --wav space.wav"
    Write-Host "  8bms soundpack platformer -o sfx"
    Write-Host "Upgrade: re-run the installer.  Uninstall: `$env:EIGHTBMS_UNINSTALL='1'; irm .../install.ps1 | iex"
    return $true
}

$opts = @{
    all = [bool]$All; audio = [bool]$Audio; midi = [bool]$Midi; mcp = [bool]$Mcp; acp = [bool]$Acp; ml = [bool]$Ml
    Method = $Method; Source = $Source; Python = $Python; NoModifyPath = [bool]$NoModifyPath
    Uninstall = [bool]$Uninstall; Purge = [bool]$Purge
}
$ok = Install-8bms $opts
# `exit` would close the window when piped into iex, so only set an exit code when run as a file
if (-not $ok -and $PSCommandPath) { exit 1 }

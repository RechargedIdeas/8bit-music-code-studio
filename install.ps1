<#
8Bit Music Code Studio installer for Windows (PowerShell 5.1+ or 7+). Puts `8bms` on your PATH.

  irm https://raw.githubusercontent.com/RechargedIdeas/8bit-music-code-studio/main/install.ps1 | iex

Always the newest installer (raw.githubusercontent.com caches for up to 5 minutes and ignores ?query strings;
the GitHub API does not cache, and this script also replaces itself with the current one when its copy is stale):
  irm https://api.github.com/repos/RechargedIdeas/8bit-music-code-studio/contents/install.ps1 -Headers @{Accept='application/vnd.github.raw'} | iex

With options, set env vars before the one-liner:
  $env:EIGHTBMS_EXTRAS = "all"       # all | audio,midi,mcp,acp,ml
  $env:EIGHTBMS_METHOD = "venv"      # pipx | uv | venv  (default auto: pipx, then uv, then a venv)
  $env:EIGHTBMS_DEBUG = "1"          # print diagnostics (paths, env, cmd.exe AutoRun) and every command
  $env:EIGHTBMS_UNINSTALL = "1"      # remove (add $env:EIGHTBMS_PURGE = "1" to delete ~/.8bms too)
or download and run it:
  irm .../install.ps1 -OutFile install.ps1; .\install.ps1 -All -Verbose
  .\install.ps1 -Uninstall [-Purge]

Options: -All -Audio -Midi -Mcp -Acp -Ml, -Method auto|pipx|uv|venv, -Source <folder|url>,
         -Python <path>, -NoModifyPath, -NoSelfUpdate, -Uninstall, -Purge, -Verbose
Missing or broken pipx/uv are installed or repaired automatically (user-level, never admin), and if a
method fails the next one is tried: pipx -> uv -> a private venv in ~/.8bms. Re-running upgrades in place.
#>
[CmdletBinding()]
param(
    [switch]$All, [switch]$Audio, [switch]$Midi, [switch]$Mcp, [switch]$Acp, [switch]$Ml,
    [ValidateSet("auto", "pipx", "uv", "venv")][string]$Method = "auto",
    [string]$Source = "",
    [string]$Python = "",
    [switch]$NoModifyPath,
    [switch]$NoSelfUpdate,
    [switch]$Uninstall,
    [switch]$Purge
)

$InstallerVersion = "1.1.1"
$RepoPath = "RechargedIdeas/8bit-music-code-studio"

function Install-8bms {
    param($Opt)
    $ErrorActionPreference = "Stop"
    $Pkg = "eightbit-music-code-studio"
    $Repo = "https://github.com/$RepoPath"
    $OnWindows = ($PSVersionTable.PSEdition -eq "Desktop") -or $IsWindows
    $Dbg = ($env:EIGHTBMS_DEBUG -eq "1") -or ($VerbosePreference -eq "Continue")
    $ExeSuffix = if ($OnWindows) { ".exe" } else { "" }

    function Say($m) { Write-Host "==> $m" -ForegroundColor Cyan }
    function Ok($m) { Write-Host " ok $m" -ForegroundColor Green }
    function Warn($m) { Write-Host "warn $m" -ForegroundColor Yellow }
    function Err($m) { Write-Host "error $m" -ForegroundColor Red }
    function Dbg($m) { if ($Dbg) { Write-Host "  .. $m" -ForegroundColor DarkGray } }
    function Have($c) { [bool](Get-Command $c -CommandType Application -ErrorAction SilentlyContinue) }
    function Q([string]$s) { if ($s -match '[\s"]') { '"' + ($s -replace '"', '\"') + '"' } else { $s } }
    # Run a native command with its output visible; on failure print the command line and exit code.
    function Run([string]$exe, [string[]]$a) {
        $ErrorActionPreference = "Continue"
        $line = (@($exe) + $a | ForEach-Object { Q $_ }) -join " "
        Dbg "> $line"
        $global:LASTEXITCODE = 0
        try { & $exe @a | Out-Host; $code = $LASTEXITCODE } catch { Write-Host "  $($_.Exception.Message)"; $code = "not runnable" }
        if ($null -eq $code) { $code = 0 }
        if ($code -ne 0) { Write-Host "  command failed (exit $code): $line" -ForegroundColor Yellow; return $false }
        return $true
    }
    # Run quietly; true if it exits 0.
    function Probe([string]$exe, [string[]]$a) {
        $ErrorActionPreference = "Continue"
        $global:LASTEXITCODE = 0
        try { & $exe @a *> $null; $ok = ($LASTEXITCODE -eq 0) } catch { $ok = $false }
        Dbg "probe $((@($exe) + $a | ForEach-Object { Q $_ }) -join ' ') -> $(if ($ok) { 'ok' } else { 'FAILED' })"
        return $ok
    }
    function Capture([string]$exe, [string[]]$a) {
        $ErrorActionPreference = "Continue"
        try { $o = (& $exe @a 2>$null | Out-String).Trim(); if ($LASTEXITCODE -eq 0) { return $o } } catch { }
        return $null
    }
    function PathUsable([string]$p) {
        if (-not $p) { return $true }
        try { $root = [IO.Path]::GetPathRoot($p) } catch { return $false }
        if ($root -and -not (Test-Path -LiteralPath $root)) { return $false }
        return $true
    }

    # ---- environment that breaks pip/pipx/uv: fix for this run only (restored at the end) ----
    $saved = @{}
    function SetEnvForRun($n, $v) { if (-not $saved.ContainsKey($n)) { $saved[$n] = [Environment]::GetEnvironmentVariable($n) }; [Environment]::SetEnvironmentVariable($n, $v) }
    foreach ($n in "PIPX_HOME", "PIPX_BIN_DIR", "PIPX_SHARED_LIBS", "PIPX_MAN_DIR", "PIPX_GLOBAL_HOME", "PIPX_GLOBAL_BIN_DIR",
        "UV_TOOL_DIR", "UV_TOOL_BIN_DIR", "UV_CACHE_DIR", "UV_PYTHON_INSTALL_DIR", "UV_INSTALL_DIR", "PIP_CACHE_DIR", "PYTHONUSERBASE") {
        $v = [Environment]::GetEnvironmentVariable($n)
        if ($v -and -not (PathUsable $v)) { Warn "$n=$v points at a drive that does not exist; ignoring it for this install"; SetEnvForRun $n $null }
    }
    foreach ($n in "PIPX_DEFAULT_PYTHON", "UV_PYTHON") {
        $v = [Environment]::GetEnvironmentVariable($n)
        if ($v -and ($v -match '[\\/]') -and -not (Test-Path -LiteralPath $v)) { Warn "$n=$v does not exist; ignoring it for this install"; SetEnvForRun $n $null }
    }
    foreach ($n in "PYTHONHOME", "PYTHONPATH", "PIP_TARGET", "PIP_PREFIX", "PIP_REQUIRE_VIRTUALENV", "PIP_USER", "VIRTUAL_ENV", "CONDA_PREFIX") {
        $v = [Environment]::GetEnvironmentVariable($n)
        if ($v) { Dbg "$n=$v (cleared for this install)"; SetEnvForRun $n $null }
    }
    foreach ($n in "TEMP", "TMP") {
        $v = [Environment]::GetEnvironmentVariable($n)
        if ($v -and -not (Test-Path -LiteralPath $v)) {
            $fb = Join-Path ([IO.Path]::GetTempPath()) ""
            if (-not (Test-Path -LiteralPath $fb)) { $fb = Join-Path $HOME ".8bms\tmp" }
            New-Item -ItemType Directory -Force -Path $fb -ErrorAction SilentlyContinue | Out-Null
            Warn "$n=$v does not exist; using $fb for this install"; SetEnvForRun $n $fb
        }
    }

    try {
        return (Install-Core)
    } finally {
        foreach ($k in $saved.Keys) { [Environment]::SetEnvironmentVariable($k, $saved[$k]) }
    }
}

function Install-Core {
    $HomeDir = if ($env:EIGHTBMS_HOME) { $env:EIGHTBMS_HOME } else { Join-Path $HOME ".8bms" }
    $Venv = Join-Path $HomeDir "venv"
    $BinDir = Join-Path $HomeDir "bin"
    $VenvBin = if ($OnWindows) { Join-Path $Venv "Scripts" } else { Join-Path $Venv "bin" }
    $VenvExe = Join-Path $VenvBin "8bms$ExeSuffix"
    $VenvPy = Join-Path $VenvBin "python$ExeSuffix"

    # ---- which commit are we installing? (also used to spot a stale cached installer) ----
    $commit = $env:EIGHTBMS_COMMIT
    $src = if ($Opt.Source) { $Opt.Source } elseif ($env:EIGHTBMS_SOURCE) { $env:EIGHTBMS_SOURCE } else { $null }
    $uninstalling = $Opt.Uninstall -or $env:EIGHTBMS_UNINSTALL -eq "1"
    if (-not $src -and -not $uninstalling) {
        if (-not $commit) {
            try { $commit = (Invoke-RestMethod -UseBasicParsing -TimeoutSec 15 -Uri "https://api.github.com/repos/$RepoPath/commits/main" -Headers @{ Accept = "application/vnd.github.sha" }).ToString().Trim() } catch { Dbg "commit lookup failed: $($_.Exception.Message)" }
        }
        if ($commit -match '^[0-9a-f]{40}$') { $src = "$Repo/archive/$commit.zip" } else { $commit = $null; $src = "$Repo/archive/refs/heads/main.zip" }
    }
    $short = if ($commit) { $commit.Substring(0, 7) } else { "main" }
    Say "8Bit Music Code Studio installer $InstallerVersion (app commit $short; PowerShell $($PSVersionTable.PSVersion))"
    if (-not $src) { $src = "$Repo/archive/refs/heads/main.zip" }
    if (Test-Path $src) { $src = "file:///" + (((Resolve-Path $src).Path -replace "\\", "/").TrimStart("/")) }
    elseif ($src -match "^https://github\.com/.+\.git$") { $src = "git+$src" }

    $extras = New-Object System.Collections.Generic.List[string]
    foreach ($n in "all", "audio", "midi", "mcp", "acp", "ml") { if ($Opt[$n]) { $extras.Add($n) } }
    if ($env:EIGHTBMS_EXTRAS) { foreach ($e in ($env:EIGHTBMS_EXTRAS -split "[,\s]+")) { if ($e -and -not $extras.Contains($e)) { $extras.Add($e) } } }
    function Spec { if ($extras.Count) { "$Pkg[$($extras -join ',')] @ $src" } else { "$Pkg @ $src" } }

    # ---- find Python 3.10+ (prefer one with tkinter), resolved to its base interpreter ----
    $check = "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)"
    $resolve = "import sys; print(getattr(sys, '_base_executable', '') or sys.executable if sys.prefix != sys.base_prefix else sys.executable)"
    $pyPath = $null
    $cands = @()
    $wantPy = if ($Opt.Python) { $Opt.Python } elseif ($env:EIGHTBMS_PYTHON) { $env:EIGHTBMS_PYTHON } else { $null }
    if ($wantPy) { $cands += , @($wantPy) }
    if (Have py) { foreach ($v in "3.13", "3.12", "3.11", "3.10") { $cands += , @("py", "-$v") } }
    foreach ($c in "python", "python3") { if (Have $c) { $cands += , @($c) } }
    foreach ($pass in 1, 2) {
        foreach ($c in $cands) {
            $exe = $c[0]; $a = @($c | Select-Object -Skip 1)
            $code = if ($pass -eq 1) { "import tkinter; $check" } else { $check }
            if (Probe $exe ($a + @("-c", $code))) {
                $p = Capture $exe ($a + @("-c", $resolve))
                if ($p -and (Test-Path -LiteralPath $p) -and (Probe $p @("-c", $check))) { $pyPath = $p; break }
            }
        }
        if ($pyPath) { break }
    }
    if ($pyPath) { Ok "Python $(Capture $pyPath @('-c', 'import platform; print(platform.python_version())')) at $pyPath" }
    elseif ($wantPy) { Warn "$wantPy is not a working Python 3.10+" }

    # ---- diagnostics ----
    function Diagnostics {
        Write-Host "---- diagnostics (installer $InstallerVersion, commit $short) ----" -ForegroundColor DarkGray
        Write-Host "  PowerShell $($PSVersionTable.PSVersion) $($PSVersionTable.PSEdition) on $([Environment]::OSVersion.VersionString)"
        Write-Host "  python: $(if ($pyPath) { $pyPath } else { '(none found)' })"
        foreach ($c in "python", "py", "pipx", "uv", "8bms") {
            foreach ($g in @(Get-Command $c -All -ErrorAction SilentlyContinue)) { Write-Host "  $c -> $($g.Source)" }
        }
        foreach ($n in "HOME", "USERPROFILE", "LOCALAPPDATA", "APPDATA", "TEMP", "TMP", "ComSpec") {
            $v = [Environment]::GetEnvironmentVariable($n)
            if ($v) { Write-Host "  $n=$v $(if (Test-Path -LiteralPath $v) { '(exists)' } else { '(MISSING)' })" }
        }
        foreach ($k in [Environment]::GetEnvironmentVariables().Keys | Sort-Object) {
            if ($k -match '^(PIPX_|UV_|PIP_|PYTHON|VIRTUAL_ENV|CONDA)') { Write-Host "  $k=$([Environment]::GetEnvironmentVariable($k))" }
        }
        if ($OnWindows) {
            foreach ($hive in "HKCU", "HKLM") {
                try {
                    $ar = (Get-ItemProperty -Path "${hive}:\Software\Microsoft\Command Processor" -Name AutoRun -ErrorAction Stop).AutoRun
                    Write-Host "  cmd.exe AutoRun ($hive): $ar"
                } catch { Write-Host "  cmd.exe AutoRun ($hive): (none)" }
            }
            try { Write-Host "  LongPathsEnabled: $((Get-ItemProperty 'HKLM:\SYSTEM\CurrentControlSet\Control\FileSystem' -Name LongPathsEnabled -ErrorAction Stop).LongPathsEnabled)" } catch { }
        }
        if ($pyPath) {
            $pv = Capture $pyPath @('-m', 'pip', '--version'); Write-Host "  python -m pip: $(if ($pv) { $pv } else { '(not installed or broken)' })"
            $pv = Capture $pyPath @('-m', 'pipx', '--version'); Write-Host "  python -m pipx: $(if ($pv) { $pv } else { '(not installed or broken)' })"
            $pe = Capture $pyPath @("-m", "pipx", "environment")
            if ($pe) { foreach ($l in ($pe -split "`n")) { if ($l -match "^PIPX_(HOME|BIN_DIR|SHARED_LIBS|LOCAL_VENVS)=") { Write-Host "  pipx $($l.Trim())" } } }
        }
        Write-Host "---- end diagnostics ----" -ForegroundColor DarkGray
    }
    if ($OnWindows) {
        foreach ($hive in "HKCU", "HKLM") {
            try {
                $ar = (Get-ItemProperty -Path "${hive}:\Software\Microsoft\Command Processor" -Name AutoRun -ErrorAction Stop).AutoRun
                if ($ar) { Warn "cmd.exe AutoRun is set ($hive): $ar  - if it points at a missing file, every cmd.exe prints 'The system cannot find the path specified.' (this installer avoids cmd.exe)" }
            } catch { }
        }
    }
    if ($Dbg) { Diagnostics }

    # ---- uninstall ----
    if ($uninstalling) {
        Say "Uninstalling 8bms"
        $removed = $false
        if ($pyPath -and (Probe $pyPath @("-m", "pipx", "--version"))) {
            if ((Capture $pyPath @("-m", "pipx", "list", "--short")) -match "(?m)^$Pkg ") { $removed = (Run $pyPath @("-m", "pipx", "uninstall", $Pkg)) -or $removed }
        }
        $ue = $null; $ua = @()
        if (Probe "uv" @("--version")) { $ue = "uv" } elseif ($pyPath -and (Probe $pyPath @("-m", "uv", "--version"))) { $ue = $pyPath; $ua = @("-m", "uv") }
        if ($ue) {
            if ((Capture $ue ($ua + @("tool", "list"))) -match "(?m)^$Pkg ") { $removed = (Run $ue ($ua + @("tool", "uninstall", $Pkg))) -or $removed }
        }
        if (Test-Path $Venv) { Remove-Item -Recurse -Force $Venv; $removed = $true }
        foreach ($f in "8bms.cmd", "8bms.exe", "8bms") { $p = Join-Path $BinDir $f; if (Test-Path $p) { Remove-Item -Force $p } }
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

    $m = $Opt.Method
    if ($env:EIGHTBMS_METHOD -and $m -eq "auto") { $m = $env:EIGHTBMS_METHOD.ToLower() }
    if ($m -notin "auto", "pipx", "uv", "venv") { Warn "unknown method '$m'; using auto"; $m = "auto" }
    $methods = if ($m -eq "auto") { @("pipx", "uv", "venv") } else { @($m) }
    if (-not $pyPath) {
        Warn "no working Python 3.10+ found; uv will install one"
        $methods = @("uv")
    }

    # ---- pip / pipx / uv bootstrapping (always through the found Python, never a pipx/uv shim) ----
    function EnsurePip {
        if (Probe $pyPath @("-m", "pip", "--version")) { return $true }
        Say "pip is missing for $pyPath; bootstrapping it (ensurepip)"
        $null = Run $pyPath @("-m", "ensurepip", "--upgrade", "--user")
        return (Probe $pyPath @("-m", "pip", "--version"))
    }
    function PipUser([string[]]$pkgs) {
        if (-not (EnsurePip)) { return $false }
        return (Run $pyPath (@("-m", "pip", "install", "--user", "--upgrade", "--disable-pip-version-check", "--no-warn-script-location") + $pkgs))
    }
    function EnsurePipx {
        if (Probe $pyPath @("-m", "pipx", "--version")) { return $true }
        Say "pipx is not installed for this Python (or is broken); installing it: python -m pip install --user pipx"
        if (-not (PipUser @("pipx"))) { return $false }
        if (-not (Probe $pyPath @("-m", "pipx", "--version"))) { Warn "pipx installed but 'python -m pipx' still fails"; return $false }
        $null = Run $pyPath @("-m", "pipx", "ensurepath")
        return $true
    }
    $script:uvCmd = $null
    function EnsureUv {
        if ($script:uvCmd) { return $true }
        if (Probe "uv" @("--version")) { $script:uvCmd = @("uv"); return $true }
        if ((Have uv)) { Warn "a uv command is on PATH but does not run; ignoring it" }
        if ($pyPath) {
            if (-not (Probe $pyPath @("-m", "uv", "--version"))) {
                Say "uv is not installed; installing it: python -m pip install --user uv"
                $null = PipUser @("uv")
            }
            if (Probe $pyPath @("-m", "uv", "--version")) { $script:uvCmd = @($pyPath, "-m", "uv"); return $true }
        }
        Say "installing uv with the official installer (astral.sh)"
        $uvHome = if ($env:UV_INSTALL_DIR) { $env:UV_INSTALL_DIR } else { Join-Path $HOME ".local\bin" }
        try {
            if ($OnWindows) {
                $ps = (Get-Process -Id $PID).Path
                $null = Run $ps @("-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", "`$env:UV_NO_MODIFY_PATH='1'; irm https://astral.sh/uv/install.ps1 | iex")
            } else {
                $null = Run "sh" @("-c", "curl -LsSf https://astral.sh/uv/install.sh | env UV_NO_MODIFY_PATH=1 sh")
            }
        } catch { Warn "uv installer failed: $($_.Exception.Message)" }
        $u = Join-Path $uvHome "uv$ExeSuffix"
        if ((Test-Path $u) -and (Probe $u @("--version"))) { $script:uvCmd = @($u); return $true }
        return $false
    }
    function UvRun([string[]]$a) { $e = $script:uvCmd[0]; $pre = @($script:uvCmd | Select-Object -Skip 1); return (Run $e ($pre + $a)) }
    function UvOut([string[]]$a) { $e = $script:uvCmd[0]; $pre = @($script:uvCmd | Select-Object -Skip 1); return (Capture $e ($pre + $a)) }

    $script:exe8 = $null
    $script:pipxRepaired = $false
    function InstallPipx([string]$spec) {
        if (-not (EnsurePipx)) { return $false }
        $args1 = @("-m", "pipx", "install", "--force", "--python", $pyPath, $spec)
        if (-not (Run $pyPath $args1)) {
            if ($script:pipxRepaired) { return $false }
            $script:pipxRepaired = $true
            Warn "pipx install failed; repairing pipx (upgrade it, reset its shared libraries and the old 8bms env) and retrying once"
            $null = PipUser @("pipx")
            $shared = Capture $pyPath @("-m", "pipx", "environment", "--value", "PIPX_SHARED_LIBS")
            if ($shared -and (Test-Path -LiteralPath $shared)) { Dbg "removing $shared"; Remove-Item -Recurse -Force -LiteralPath $shared -ErrorAction SilentlyContinue }
            $venvs = Capture $pyPath @("-m", "pipx", "environment", "--value", "PIPX_LOCAL_VENVS")
            if ($venvs) { $old = Join-Path $venvs $Pkg; if (Test-Path -LiteralPath $old) { Dbg "removing $old"; Remove-Item -Recurse -Force -LiteralPath $old -ErrorAction SilentlyContinue } }
            if (-not (Run $pyPath $args1)) { return $false }
        }
        $d = Capture $pyPath @("-m", "pipx", "environment", "--value", "PIPX_BIN_DIR")
        if (-not $d) { $d = Join-Path $HOME ".local\bin" }
        $script:exe8 = Join-Path $d "8bms$ExeSuffix"
        return $true
    }
    function InstallUv([string]$spec) {
        if (-not (EnsureUv)) { return $false }
        $p = if ($pyPath) { $pyPath } else { "3.12" }
        if (-not (UvRun @("tool", "install", "--force", "--reinstall", "--python", $p, $spec))) { return $false }
        $d = UvOut @("tool", "dir", "--bin")
        if (-not $d) { $d = Join-Path $HOME ".local\bin" }
        $script:exe8 = Join-Path $d "8bms$ExeSuffix"
        return $true
    }
    function NewVenv {
        if ((Test-Path $VenvPy) -and (Probe $VenvPy @("-c", "import sys"))) { return $true }
        if (Test-Path $Venv) { Warn "removing a broken venv at $Venv"; Remove-Item -Recurse -Force $Venv }
        New-Item -ItemType Directory -Force -Path $HomeDir | Out-Null
        if (Run $pyPath @("-m", "venv", $Venv)) { return $true }
        Warn "python -m venv failed; trying a venv without pip plus ensurepip"
        if (Test-Path $Venv) { Remove-Item -Recurse -Force $Venv }
        if ((Run $pyPath @("-m", "venv", "--without-pip", $Venv)) -and (Run $VenvPy @("-m", "ensurepip", "--upgrade"))) { return $true }
        Warn "trying virtualenv instead"
        if (Test-Path $Venv) { Remove-Item -Recurse -Force $Venv }
        if ((Probe $pyPath @("-m", "virtualenv", "--version")) -or (PipUser @("virtualenv"))) {
            if (Run $pyPath @("-m", "virtualenv", $Venv)) { return $true }
        }
        if (EnsureUv) {
            if (Test-Path $Venv) { Remove-Item -Recurse -Force $Venv }
            if (UvRun @("venv", "--seed", "--python", $pyPath, $Venv)) { return $true }
        }
        Err "could not create a virtualenv at $Venv"
        return $false
    }
    function InstallVenv([string]$spec) {
        if (-not (NewVenv)) { return $false }
        if (-not (Probe $VenvPy @("-m", "pip", "--version"))) { $null = Run $VenvPy @("-m", "ensurepip", "--upgrade") }
        $pipq = @("-m", "pip", "install", "-q", "--disable-pip-version-check")
        $null = Run $VenvPy ($pipq + @("--upgrade", "pip"))
        if (-not (Run $VenvPy ($pipq + @("--upgrade", $spec)))) { return $false }
        # same version number on every main commit: force-refresh the app itself (not numpy etc.)
        if (-not (Run $VenvPy ($pipq + @("--force-reinstall", "--no-deps", $spec)))) { return $false }
        New-Item -ItemType Directory -Force -Path $BinDir | Out-Null
        foreach ($f in "8bms.cmd", "8bms.exe", "8bms") { $p = Join-Path $BinDir $f; if (Test-Path $p) { Remove-Item -Force $p -ErrorAction SilentlyContinue } }
        if ($OnWindows) {
            # copy the console-script launcher (it holds the absolute venv python path); no .cmd, so cmd.exe is never involved
            $dst = Join-Path $BinDir "8bms.exe"
            Copy-Item -Force $VenvExe $dst
            $script:exe8 = $dst
        } else {
            $dst = Join-Path $BinDir "8bms"
            New-Item -ItemType SymbolicLink -Path $dst -Target $VenvExe | Out-Null
            $script:exe8 = $dst
        }
        return $true
    }
    function TryInstall([string]$how, [string]$spec) {
        try {
            switch ($how) { "pipx" { return (InstallPipx $spec) } "uv" { return (InstallUv $spec) } "venv" { return (InstallVenv $spec) } }
        } catch { Warn "$how failed: $($_.Exception.Message)"; return $false }
    }

    $installed = $false
    foreach ($how in $methods) {
        $spec = Spec
        Say "Installing with ${how}: $spec"
        $okNow = TryInstall $how $spec
        if (-not $okNow -and $extras.Count) {
            Warn "extras [$($extras -join ',')] failed to install (often: no prebuilt wheel for this Python, e.g. python-rtmidi)."
            Warn "installing the core app without them; re-run with the flag later to add them."
            $extras.Clear()
            $okNow = TryInstall $how (Spec)
        }
        if ($okNow) {
            $e = $script:exe8
            if (-not ($e -and (Test-Path $e))) { $g = Get-Command 8bms -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1; if ($g) { $e = $g.Source } }
            if ($e -and (Test-Path $e) -and (Probe $e @("--version"))) { $script:exe8 = $e; $m = $how; $installed = $true; break }
            Warn "$how finished but $(if ($e) { $e } else { '8bms' }) does not run"
        }
        if ($how -ne $methods[-1]) { Warn "install with $how failed; trying the next method" }
    }
    if (-not $installed) {
        Diagnostics
        Err "install failed with: $($methods -join ', '). The messages above show each failing command and its exit code."
        Write-Host "   Please copy everything above into an issue: $Repo/issues/new" -ForegroundColor Red
        return $false
    }

    $exe8 = $script:exe8
    $ver = Capture $exe8 @("--version")
    Ok "$ver -> $exe8 (via $m)"

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
    $first = Get-Command 8bms -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($first -and ($first.Source -ne $exe8)) { Warn "another 8bms comes first on PATH: $($first.Source) (remove it or put $dir first)" }

    $tkPy = if ($m -eq "venv") { $VenvPy } else { $pyPath }
    if ($tkPy -and -not (Probe $tkPy @("-c", "import tkinter"))) { Warn "tkinter is missing, so the GUI won't open (CLI/MCP/ACP/HTTP work). Reinstall Python from python.org with 'tcl/tk and IDLE' ticked." }
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

# ---- a stale copy (CDN cache) hands over to the current installer of the commit being installed ----
function Get-FreshInstaller {
    param($Opt)
    if ($Opt.NoSelfUpdate -or $env:EIGHTBMS_NO_SELFUPDATE -eq "1") { return $null }
    $url = $env:EIGHTBMS_INSTALLER_URL
    if (-not $url) {
        if ($PSCommandPath -or $Opt.Source -or $env:EIGHTBMS_SOURCE) { return $null }   # run from a file / local source: use as is
        $sha = $env:EIGHTBMS_COMMIT
        if (-not $sha) {
            try {
                $sha = (Invoke-RestMethod -UseBasicParsing -TimeoutSec 15 -Uri "https://api.github.com/repos/$RepoPath/commits/main" -Headers @{ Accept = "application/vnd.github.sha" }).ToString().Trim()
            } catch { return $null }
        }
        if ($sha -notmatch '^[0-9a-f]{40}$') { return $null }
        $env:EIGHTBMS_COMMIT = $sha
        $url = "https://raw.githubusercontent.com/$RepoPath/$sha/install.ps1"
    }
    try {
        $text = if (Test-Path -LiteralPath $url) { Get-Content -Raw -LiteralPath $url } else { [string](Invoke-RestMethod -UseBasicParsing -TimeoutSec 30 -Uri $url) }
    } catch { return $null }
    if ($text -match '(?m)^\$InstallerVersion = "([^"]+)"' -and $Matches[1] -ne $InstallerVersion) {
        Write-Host "warn this installer copy ($InstallerVersion) is stale (cached download); running the current installer $($Matches[1])" -ForegroundColor Yellow
        return $text
    }
    return $null
}

try { [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12 } catch { }
$opts = @{
    all = [bool]$All; audio = [bool]$Audio; midi = [bool]$Midi; mcp = [bool]$Mcp; acp = [bool]$Acp; ml = [bool]$Ml
    Method = $Method; Source = $Source; Python = $Python; NoModifyPath = [bool]$NoModifyPath; NoSelfUpdate = [bool]$NoSelfUpdate
    Uninstall = [bool]$Uninstall; Purge = [bool]$Purge
}
$global:EIGHTBMS_INSTALL_OK = $false
$hadCommit = [bool]$env:EIGHTBMS_COMMIT
try {
    $fresh = Get-FreshInstaller $opts
    if ($fresh) {
        $env:EIGHTBMS_NO_SELFUPDATE = "1"
        $bound = @{}
        if ($PSBoundParameters) { foreach ($k in $PSBoundParameters.Keys) { $bound[$k] = $PSBoundParameters[$k] } }
        try { & ([scriptblock]::Create($fresh)) @bound } finally { Remove-Item Env:\EIGHTBMS_NO_SELFUPDATE -ErrorAction SilentlyContinue }
        $ok = [bool]$global:EIGHTBMS_INSTALL_OK
    } else {
        $ok = [bool](Install-8bms $opts)
        $global:EIGHTBMS_INSTALL_OK = $ok
    }
} finally {
    if (-not $hadCommit) { Remove-Item Env:\EIGHTBMS_COMMIT -ErrorAction SilentlyContinue }
}
# don't leak a probe's native exit code (e.g. a missing uv) as the script's result
$global:LASTEXITCODE = if ($ok) { 0 } else { 1 }
# `exit` would close the window when piped into iex, so only set an exit code when run as a file
if (-not $ok -and $PSCommandPath) { exit 1 }

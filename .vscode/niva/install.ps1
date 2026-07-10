# Install niva syntax highlighting for every editor found on this machine (Windows).
# PowerShell port of install.sh, for Windows users who don't have bash.
# Idempotent: safe to re-run. Per-user only (no admin).
#
#   powershell -ExecutionPolicy Bypass -File .vscode\niva\install.ps1
#
# (If script execution is blocked, the -ExecutionPolicy Bypass above runs it for this one call
#  without changing your machine policy.)

# NOTE: deliberately NOT 'Stop'. Native tools here (npm, npx/vsce, code) write progress and warnings
# to stderr; under 'Stop', Windows PowerShell turns any such stderr line into a terminating error and
# aborts the whole install (e.g. vsce's harmless "LICENSE not found" warning). We check $LASTEXITCODE
# and use -ErrorAction on cmdlets instead.
$ErrorActionPreference = 'Continue'
$HERE = $PSScriptRoot
$script:did = $false

function Note([string]$msg) { Write-Host "  + $msg" -ForegroundColor Green; $script:did = $true }
function Warn([string]$msg) { Write-Host "  ! $msg" -ForegroundColor Yellow }

# Find QGIS's python-qgis.bat (OSGeo4W install, or a standalone "QGIS x.y" under Program Files).
function Find-QgisBat {
  $osgeo = Join-Path $env:SystemDrive 'OSGeo4W\bin\python-qgis.bat'
  if (Test-Path $osgeo) { return $osgeo }
  foreach ($base in $env:ProgramFiles, ${env:ProgramFiles(x86)}) {
    if ($base) {
      $hit = Get-ChildItem -Path (Join-Path $base 'QGIS*\bin\python-qgis.bat') -ErrorAction SilentlyContinue |
             Select-Object -First 1
      if ($hit) { return $hit.FullName }
    }
  }
  return $null
}

# Point the VS Code language server at QGIS's Python. The extension defaults to a bare `niva`
# command, which on Windows isn't on PATH -- niva runs through python-qgis.bat. We only auto-write a
# settings.json we create ourselves; an existing one is never rewritten (we print the snippet so you
# add it by hand, keeping your comments/formatting intact).
function Set-NivaLspSetting([string]$settingsPath, [string]$bat) {
  $snippet = '  "niva.lsp.command": ' + ($bat | ConvertTo-Json) + ",`n" +
             '  "niva.lsp.args": ["-m", "niva.cli.main", "lsp"]'
  if (-not (Test-Path $settingsPath)) {
    $body = "{`n$snippet`n}`n"
    [System.IO.File]::WriteAllText($settingsPath, $body)   # UTF-8, no BOM
    Note "VS Code settings -> $settingsPath (niva.lsp.command set to QGIS's python-qgis.bat)"
    return
  }
  $raw = Get-Content -Raw -Path $settingsPath
  if ($raw -match '"niva\.lsp\.command"') {
    Note "VS Code settings already set niva.lsp.command ($settingsPath) -- left as-is"
    return
  }
  Warn "Add these two lines to $settingsPath (inside the outer { }), then reload VS Code:"
  Write-Host $snippet -ForegroundColor Cyan
}

# --- VS Code / VSCodium -- grammar + snippets + LANGUAGE SERVER (installed as a proper .vsix) ---
# Modern VS Code reliably loads only extensions it installed itself (a manually-copied folder is
# ignored), so we PACKAGE a .vsix (which bundles the language-server client) and install it through
# the editor's CLI. Building a fresh .vsix needs Node/npm; if npm is absent but a .vsix was built
# before, we install that one.
$vscli = $null
foreach ($c in 'code', 'codium', 'code-insiders') {
  $cmd = Get-Command $c -ErrorAction SilentlyContinue
  if ($cmd) { $vscli = $cmd; break }
}
if ($vscli) {
  $vsix = Join-Path $HERE 'niva.vsix'
  $haveNpm = [bool](Get-Command npm -ErrorAction SilentlyContinue)

  # Remove any stale manually-copied folder from older installs so it can't shadow the .vsix.
  foreach ($stale in "$env:USERPROFILE\.vscode\extensions\niva", "$env:USERPROFILE\.vscodium\extensions\niva") {
    if (Test-Path $stale) { Remove-Item -Recurse -Force $stale -ErrorAction SilentlyContinue }
  }

  $built = $false
  if ($haveNpm) {
    Push-Location $HERE
    try {
      & npm install --omit=dev --no-audit --no-fund 2>$null | Out-Null
      if ($LASTEXITCODE -eq 0) {
        & npx --yes '@vscode/vsce' package --out $vsix 2>$null | Out-Null
        if ($LASTEXITCODE -eq 0) { $built = $true }
      }
    } finally { Pop-Location }
    if (-not $built) { Warn "Could not build the VS Code .vsix -- see docs/guide/editor-integration.md" }
  } elseif (-not (Test-Path $vsix)) {
    Warn "VS Code found but npm is missing -- install Node.js, then re-run, for the language server."
  }

  if ($built -or (Test-Path $vsix)) {
    & $vscli.Source --install-extension $vsix --force 2>$null | Out-Null
    if ($LASTEXITCODE -eq 0) {
      Note "VS Code ($($vscli.Name)) -> niva extension installed WITH language server (reload the window)"
    } else {
      Note "VS Code -> built $vsix -- install it via Extensions => ... => Install from VSIX..."
    }
  }

  # Wire the language server to QGIS's Python, unless a real `niva` launcher is already on PATH
  # (in which case the extension's default command works as-is). -CommandType Application is
  # essential: without it a `niva` *function* in the user's PowerShell $PROFILE (which `powershell
  # -File` loads) is mistaken for a real command — and that function is invisible to VS Code.
  if (-not (Get-Command niva -CommandType Application -ErrorAction SilentlyContinue)) {
    $bat = Find-QgisBat
    if ($bat) {
      $apps = @('Code', 'VSCodium')
      $wroteAny = $false
      foreach ($app in $apps) {
        $userDir = Join-Path $env:APPDATA "$app\User"
        if (Test-Path $userDir) { Set-NivaLspSetting (Join-Path $userDir 'settings.json') $bat; $wroteAny = $true }
      }
      if (-not $wroteAny) { Warn "No VS Code user dir yet -- launch VS Code once, then re-run to auto-set niva.lsp.command." }
    } else {
      Warn "Couldn't find QGIS's python-qgis.bat -- set niva.lsp.command manually (docs/guide/editor-integration.md)."
    }
  }
}

# --- Notepad++ (Windows) -- drop the User Defined Language into the auto-loaded folder ---
# Notepad++ loads every .xml under %APPDATA%\Notepad++\userDefineLangs at startup, so this needs no
# manual "Import..." step. We only act if Notepad++ has a config dir (i.e. it's installed & been run).
$nppData = Join-Path $env:APPDATA 'Notepad++'
if (Test-Path $nppData) {
  $udlDir = Join-Path $nppData 'userDefineLangs'
  New-Item -ItemType Directory -Force -Path $udlDir | Out-Null
  Copy-Item (Join-Path $HERE 'npp\niva.udl.xml') (Join-Path $udlDir 'niva.udl.xml') -Force
  Note "Notepad++ -> $udlDir\niva.udl.xml (restart Notepad++)"
}

# --- Vim (syntax + filetype detection) -- Windows uses %USERPROFILE%\vimfiles ---
if (Get-Command vim -ErrorAction SilentlyContinue) {
  $d = Join-Path $env:USERPROFILE 'vimfiles'
  New-Item -ItemType Directory -Force -Path (Join-Path $d 'syntax'), (Join-Path $d 'ftdetect') | Out-Null
  Copy-Item (Join-Path $HERE 'vim\niva.vim') (Join-Path $d 'syntax\niva.vim') -Force
  Set-Content -Path (Join-Path $d 'ftdetect\niva.vim') `
    -Value 'au BufRead,BufNewFile *.niva set filetype=niva' -Encoding ascii
  Note "Vim -> $d\{syntax,ftdetect}\niva.vim"
}

# --- Neovim (syntax + filetype detection) -- Windows uses %LOCALAPPDATA%\nvim ---
if (Get-Command nvim -ErrorAction SilentlyContinue) {
  $d = Join-Path $env:LOCALAPPDATA 'nvim'
  New-Item -ItemType Directory -Force -Path (Join-Path $d 'syntax'), (Join-Path $d 'ftdetect') | Out-Null
  Copy-Item (Join-Path $HERE 'vim\niva.vim') (Join-Path $d 'syntax\niva.vim') -Force
  Set-Content -Path (Join-Path $d 'ftdetect\niva.vim') `
    -Value 'au BufRead,BufNewFile *.niva set filetype=niva' -Encoding ascii
  Note "Neovim -> $d\{syntax,ftdetect}\niva.vim"
}

# GtkSourceView (Mousepad/gedit/...) and Kate/KWrite are Linux desktop editors -- skipped on Windows.
# Sublime / Zed / JetBrains / bat consume the same TextMate grammar; those are manual (see docs).

if ($script:did) { Write-Host "Done -- restart your editor(s)." } else { Write-Host "No supported editors detected." }
Write-Host "Other editors (Sublime, Zed, JetBrains, bat): see docs/guide/editor-integration.md"

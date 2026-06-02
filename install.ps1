# install.ps1 — EchoMind v1.1.0 Windows 一键安装 (含开机自启)
$ErrorActionPreference = "Stop"
$SKILL_DIR = $PSScriptRoot

# Hermes 安装目录检测（优先级: 环境变量 > AppData\Local\hermes > ~\.hermes）
if ($env:HERMES_HOME) {
    $HERMES_DIR = $env:HERMES_HOME
} elseif (Test-Path "$env:LOCALAPPDATA\hermes") {
    $HERMES_DIR = "$env:LOCALAPPDATA\hermes"
} else {
    $HERMES_DIR = "$env:USERPROFILE\.hermes"
}
$PLUGIN_DIR = "$HERMES_DIR\plugins\echomind"

# EchoMind 配置目录（优先级: 环境变量 > HERMES_HOME 子目录 > %USERPROFILE%\.echomind）
if ($env:ECHOMIND_HOME) {
    $CONFIG_DIR = $env:ECHOMIND_HOME
} else {
    $CONFIG_DIR = "$env:USERPROFILE\.echomind"
}

Write-Host "=== EchoMind v1.1.0 Windows Install ==="
Write-Host "  Hermes home: $HERMES_DIR"

# 1. 安装到 Hermes
Write-Host "  [1/4] Installing to $PLUGIN_DIR"
New-Item -ItemType Directory -Force -Path $PLUGIN_DIR | Out-Null
Copy-Item -Path "$SKILL_DIR\*" -Destination $PLUGIN_DIR -Recurse -Force

# 2. 生成配置
New-Item -ItemType Directory -Force -Path $CONFIG_DIR | Out-Null
if (-not (Test-Path "$CONFIG_DIR\echomind_config.yaml")) {
    Write-Host "  [2/4] Creating default config..."
    Copy-Item -Path "$PLUGIN_DIR\echomind_config.yaml" -Destination "$CONFIG_DIR\" -ErrorAction SilentlyContinue
}

# 3. 验证
Write-Host "  [3/4] Verification..."
$python = (Get-Command python -ErrorAction SilentlyContinue).Source
if (-not $python) { $python = (Get-Command python3 -ErrorAction SilentlyContinue).Source }
# Forward-slash path avoids unicode-escape errors from backslashes (v1.1.2 fix)
$pluginDirFwd = $PLUGIN_DIR.Replace('\','/')
try {
    & $python -c "import sys; sys.path.insert(0, '$pluginDirFwd'); from core._reflective_version import get_echomind_version; print(f'EchoMind {get_echomind_version()}')"
} catch {
    Write-Host "    Warning: verification failed ($_), but files installed correctly"
}

# 4. 注册开机自启
# Step 4: HTTP service auto-start (optional, default: skipped)
# Set $env:ECHOMIND_HTTP_SERVICE=1 to enable
if ($env:ECHOMIND_HTTP_SERVICE -eq "1") {
    Write-Host "  [4/4] Setting up HTTP service auto-start..."
    $STARTUP_DIR = [Environment]::GetFolderPath("Startup")
    $VBS_PATH = "$PLUGIN_DIR\echomind_start.vbs"

    # 创建 VBS 无窗口启动器
@"
Set ws = CreateObject("WScript.Shell")
ws.Run "$python $PLUGIN_DIR\main.py", 0, False
"@ | Out-File -FilePath $VBS_PATH -Encoding ASCII

    # 注册到 Run 注册表（持久生效，不受快捷方式删除影响）
    $regPath = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Run"
    Set-ItemProperty -Path $regPath -Name "EchoMindMemory" -Value "wscript.exe `"$VBS_PATH`"" -Force

    # 同时也放到 Startup 文件夹（双重保障）
    $shortcutPath = Join-Path $STARTUP_DIR "EchoMindMemory.lnk"
    $WScriptShell = New-Object -ComObject WScript.Shell
    $Shortcut = $WScriptShell.CreateShortcut($shortcutPath)
    $Shortcut.TargetPath = "wscript.exe"
    $Shortcut.Arguments = "`"$VBS_PATH`""
    $Shortcut.WindowStyle = 7  # Minimized
    $Shortcut.Save()

    Write-Host "    Auto-start registered (Registry + Startup folder)"
} else {
    Write-Host "  [4/4] Skipped HTTP service auto-start"
    Write-Host "    Hermes plugin runs in-process — no separate service needed"
}

Write-Host ""
Write-Host "  Done!"
Write-Host ""
if ($env:ECHOMIND_HTTP_SERVICE -eq "1") {
    Write-Host "  HTTP API: http://localhost:8005"
    Write-Host "  Restart to verify auto-start, or run now: python $PLUGIN_DIR\main.py"
} else {
    Write-Host "  Hermes plugin runs in-process — ready to use"
    Write-Host "  To enable HTTP service: `$env:ECHOMIND_HTTP_SERVICE=1; .\install.ps1"
}
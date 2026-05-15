#!/bin/bash
# install.sh — EchoMind v1.1.0 一键安装 (含开机自启)
set -e

SKILL_DIR="$(dirname "$0")"
INSTALL_DIR="$HOME/.hermes/skills/echomind-memory"
PLUGIN_DIR="$HOME/.hermes/plugins/echomind"
CONFIG_DIR="$HOME/.echomind"

echo "=== EchoMind v1.1.0 Install ==="

# 1. 安装到 Hermes skill
echo "  [1/4] Installing to $INSTALL_DIR..."
mkdir -p "$INSTALL_DIR"
cp -r "$SKILL_DIR"/. "$INSTALL_DIR/"

# 2. 安装到 Hermes plugin
echo "  [2/4] Installing to $PLUGIN_DIR..."
mkdir -p "$PLUGIN_DIR"
cp -r "$INSTALL_DIR"/. "$PLUGIN_DIR/"

# 3. 生成默认配置 (保留已有)
mkdir -p "$CONFIG_DIR"
if [ ! -f "$CONFIG_DIR/echomind_config.yaml" ]; then
    echo "  [3/4] Creating default config..."
    cp "$INSTALL_DIR/echomind_config.yaml" "$CONFIG_DIR/" 2>/dev/null || true
fi

# 4. 注册开机自启
echo "  [4/4] Setting up auto-start..."
_SERVICE_DIR="$HOME/.config/systemd/user"
_SERVICE_FILE="$_SERVICE_DIR/echomind.service"
_PYTHON="$(command -v python3 || command -v python)"

if command -v systemctl &>/dev/null; then
    # Linux: systemd user service
    mkdir -p "$_SERVICE_DIR"
    cat > "$_SERVICE_FILE" << EOF
[Unit]
Description=EchoMind Memory Service
After=network.target

[Service]
Type=simple
ExecStart=$_PYTHON $PLUGIN_DIR/main.py
WorkingDirectory=$PLUGIN_DIR
Restart=on-failure
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=default.target
EOF
    systemctl --user daemon-reload
    systemctl --user enable echomind.service
    systemctl --user start echomind.service
    echo "    systemd service installed and started"

elif [[ "$(uname)" == "Darwin" ]]; then
    # macOS: launchd
    _PLIST="$HOME/Library/LaunchAgents/com.echomind.memory.plist"
    mkdir -p "$(dirname "$_PLIST")"
    cat > "$_PLIST" << EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.echomind.memory</string>
    <key>ProgramArguments</key>
    <array>
        <string>$_PYTHON</string>
        <string>$PLUGIN_DIR/main.py</string>
    </array>
    <key>WorkingDirectory</key>
    <string>$PLUGIN_DIR</string>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>$HOME/Library/Logs/echomind.log</string>
    <key>StandardErrorPath</key>
    <string>$HOME/Library/Logs/echomind.log</string>
</dict>
</plist>
EOF
    launchctl load "$_PLIST"
    echo "    launchd service installed and started"

else
    echo "    Auto-start not configured (unsupported platform)"
    echo "    Manually: python $PLUGIN_DIR/main.py"
fi

echo ""
echo "  Done!"
echo "  HTTP API: http://localhost:8005"
echo "  Service: systemctl --user status echomind"
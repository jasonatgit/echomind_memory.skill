#!/bin/bash
# install.sh — EchoMind v1.1.6 one-click install (with auto-start)
set -e

# Hermes install path detection (priority: env var > XDG > default)
if [ -n "${HERMES_HOME}" ]; then
    HERMES_HOME_DIR="${HERMES_HOME}"
elif [ -n "${XDG_DATA_HOME}" ]; then
    HERMES_HOME_DIR="${XDG_DATA_HOME}/hermes"
else
    HERMES_HOME_DIR="${HOME}/.hermes"
fi

SKILL_DIR="$(dirname "$0")"
INSTALL_DIR="${HERMES_HOME_DIR}/skills/echomind-memory"
# Backward compat: Hermes <0.16 uses plugins/ path; dual-copy ensures both work.
PLUGIN_DIR="${HERMES_HOME_DIR}/plugins/echomind"
CONFIG_DIR="${HOME}/.echomind"

echo "=== EchoMind v1.1.6 Install ==="
echo "  Hermes home: ${HERMES_HOME_DIR}"

# 1. Install to Hermes skill
echo "  [1/4] Installing to $INSTALL_DIR..."
mkdir -p "$INSTALL_DIR"
cp -r "$SKILL_DIR"/. "$INSTALL_DIR/"

# 2. Install to Hermes plugin (runtime files only)
echo "  [2/4] Installing to $PLUGIN_DIR..."
mkdir -p "$PLUGIN_DIR"
# Copy core files, exclude build/docs/test/dev files
cp -r "$INSTALL_DIR"/. "$PLUGIN_DIR/"
# Clean up files not meant for runtime deployment
rm -rf "$PLUGIN_DIR"/setup.py        "$PLUGIN_DIR"/doc        "$PLUGIN_DIR"/test        "$PLUGIN_DIR"/build        "$PLUGIN_DIR"/__pycache__        "$PLUGIN_DIR"/echomind_memory.egg-info        "$PLUGIN_DIR"/.claude        "$PLUGIN_DIR"/setup.py.bak        "$PLUGIN_DIR"/.git        "$PLUGIN_DIR"/.gitignore 2>/dev/null
find "$PLUGIN_DIR" -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
find "$PLUGIN_DIR" -name "*.pyc" -delete 2>/dev/null || true

# 3. Generate default config (preserve existing)
mkdir -p "$CONFIG_DIR"
if [ ! -f "$CONFIG_DIR/echomind_config.yaml" ]; then
    echo "  [3/4] Creating default config..."
    cp "$INSTALL_DIR/echomind_config.yaml" "$CONFIG_DIR/" 2>/dev/null || true
fi

# 4. Register auto-start (HTTP service, optional)
_AUTO_HTTP="${ECHOMIND_HTTP_SERVICE:-0}"
if [ "${_AUTO_HTTP}" = "1" ]; then
    echo "  [4/4] Setting up HTTP service auto-start..."
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

else
    echo "  [4/4] Skipped HTTP service auto-start"
    echo "    Hermes plugin runs in-process — no separate service needed"
fi

echo ""
echo "  Done!"
echo ""
if [ "${_AUTO_HTTP}" = "1" ]; then
    echo "  HTTP API: http://localhost:8005"
    echo "  Service: systemctl --user status echomind"
else
    echo "  Hermes plugin runs in-process — ready to use"
    echo "  To enable HTTP service: ECHOMIND_HTTP_SERVICE=1 ./install.sh"
fi

# ── Profile isolation info (v1.1.6+) ──────────────────────
echo ""
echo "  ╔══════════════════════════════════════════════════════╗"
echo "  ║  EchoMind Profile isolation ready                   ║"
echo "  ╠══════════════════════════════════════════════════════╣"
echo "  ║  ✅ Memory auto-isolated by Profile                   ║"
echo "  ║                                                     ║"
echo "  ║  ⚠️  For per-project isolation, configure in config.yaml ║"
echo "  ║  Add:                                                ║"
echo "  ║    memory:                                          ║"
echo "  ║      provider: echomind                             ║"
echo "  ║      project: <your-project-name>                    ║"
echo "  ║                                                     ║"
echo "  ║  Without project, defaults to global (profile-only isolation)  ║"
echo "  ╚══════════════════════════════════════════════════════╝"
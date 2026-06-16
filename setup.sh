#!/usr/bin/env bash
# Sets up the Calendar Display app on a Raspberry Pi:
#   - Python venv + dependencies
#   - systemd service (runs on boot, restarts on failure)
#   - Chromium kiosk autostart on the desktop session
#
# Run from the repo directory after `git clone` + `cp config.example.yaml config.yaml`
# (and filling in config.yaml).

set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_USER="$(whoami)"
PORT="$(python3 - "$REPO_DIR/config.yaml" <<'EOF'
import sys, yaml
with open(sys.argv[1]) as f:
    print(yaml.safe_load(f).get("port", 8080))
EOF
)"

echo "==> Repo dir: $REPO_DIR"
echo "==> User: $APP_USER"
echo "==> Port: $PORT"

if [ ! -f "$REPO_DIR/config.yaml" ]; then
  echo "config.yaml not found. Copy config.example.yaml to config.yaml and fill it in first." >&2
  exit 1
fi

# ---------- Python venv + deps ----------

echo "==> Creating virtualenv"
python3 -m venv "$REPO_DIR/venv"
"$REPO_DIR/venv/bin/pip" install --upgrade pip
"$REPO_DIR/venv/bin/pip" install -r "$REPO_DIR/requirements.txt"

# ---------- systemd service ----------

echo "==> Installing systemd service"
sudo tee /etc/systemd/system/calendardisplay.service > /dev/null <<EOF
[Unit]
Description=Calendar Display
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$APP_USER
WorkingDirectory=$REPO_DIR
ExecStart=$REPO_DIR/venv/bin/python $REPO_DIR/app.py
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable calendardisplay.service
sudo systemctl restart calendardisplay.service

# ---------- Chromium kiosk autostart ----------

echo "==> Configuring Chromium kiosk autostart"
AUTOSTART_DIR="$HOME/.config/autostart"
mkdir -p "$AUTOSTART_DIR"

cat > "$AUTOSTART_DIR/calendardisplay-kiosk.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=Calendar Display Kiosk
Exec=$REPO_DIR/kiosk.sh
X-GNOME-Autostart-enabled=true
EOF

cat > "$REPO_DIR/kiosk.sh" <<EOF
#!/usr/bin/env bash
# Disable screen blanking / DPMS, then launch Chromium in kiosk mode.
# DBUS_SESSION_BUS_ADDRESS is unset so Chromium cannot prompt for a keyring
# password — which would otherwise block startup with a modal dialog.
unset DBUS_SESSION_BUS_ADDRESS

xset s off    || true
xset s noblank || true
xset -dpms    || true

# Wait for the local server to come up (up to 30 s).
for i in \$(seq 1 30); do
  curl -sf "http://localhost:$PORT/" > /dev/null && break
  sleep 1
done

# --password-store=basic: skip keyring/wallet prompts entirely
# --kiosk: true full-screen, no address bar, no window chrome
chromium-browser \\
  --noerrdialogs \\
  --disable-infobars \\
  --kiosk \\
  --password-store=basic \\
  --no-first-run \\
  --disable-translate \\
  --disable-features=TranslateUI \\
  --check-for-update-interval=31536000 \\
  "http://localhost:$PORT"
EOF
chmod +x "$REPO_DIR/kiosk.sh"

echo "==> Done."
echo "Service status: sudo systemctl status calendardisplay"
echo "Reboot to start the kiosk display: sudo reboot"

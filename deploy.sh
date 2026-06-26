#!/usr/bin/env bash
set -euo pipefail

PI="jul@raspberry.local"
REMOTE_DIR="/home/jul/loadcounter"
SERVICE="loadcounter"
KEYBOARD_SERVICE="loadcounter-keyboard"
BLE_SERVICE="loadcounter-ble"

echo "==> Copying files to Pi..."
scp load-counter.py keyboard-listener.py loadcounter-ble.py test-ultrasonic.sensors.py "$PI:$REMOTE_DIR/"
scp loadcounter.service "$PI:/tmp/loadcounter.service"
scp loadcounter-keyboard.service "$PI:/tmp/loadcounter-keyboard.service"
scp loadcounter-ble.service "$PI:/tmp/loadcounter-ble.service"

echo "==> Ensuring BLE Python dependency..."
ssh "$PI" "$REMOTE_DIR/env/bin/python - <<'PY' || $REMOTE_DIR/env/bin/pip install dbus-next
try:
    import dbus_next
except ModuleNotFoundError:
    raise SystemExit(1)
PY"

echo "==> Installing service unit..."
ssh "$PI" "sudo mv /tmp/loadcounter.service /etc/systemd/system/loadcounter.service && sudo mv /tmp/loadcounter-keyboard.service /etc/systemd/system/loadcounter-keyboard.service && sudo mv /tmp/loadcounter-ble.service /etc/systemd/system/loadcounter-ble.service && sudo systemctl daemon-reload && sudo systemctl enable $BLE_SERVICE"

echo "==> Preparing persistent state dir..."
ssh "$PI" "sudo install -d -o daemon -g daemon /var/lib/loadcounter && sudo install -d -m 2770 -o jul -g daemon /var/tmp/loadcounter && sudo rm -f /var/tmp/loadcounter/keyboard-command.json /var/tmp/loadcounter/keyboard-command.json.tmp"

echo "==> Restarting service..."
ssh "$PI" "sudo systemctl restart $SERVICE $KEYBOARD_SERVICE $BLE_SERVICE"

echo "==> Status:"
ssh "$PI" "sudo systemctl status $SERVICE $KEYBOARD_SERVICE $BLE_SERVICE --no-pager -l"

echo ""
echo "Done. Use ./logs.sh to view logs."

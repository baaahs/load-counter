#!/usr/bin/env bash
set -euo pipefail

PI="jul@raspberry.local"
REMOTE_DIR="/home/jul/loadcounter"
SERVICE="loadcounter"
KEYBOARD_SERVICE="loadcounter-keyboard"

echo "==> Copying files to Pi..."
scp load-counter.py keyboard-listener.py test-ultrasonic.sensors.py "$PI:$REMOTE_DIR/"
scp loadcounter.service "$PI:/tmp/loadcounter.service"
scp loadcounter-keyboard.service "$PI:/tmp/loadcounter-keyboard.service"

echo "==> Installing service unit..."
ssh "$PI" "sudo mv /tmp/loadcounter.service /etc/systemd/system/loadcounter.service && sudo mv /tmp/loadcounter-keyboard.service /etc/systemd/system/loadcounter-keyboard.service && sudo systemctl daemon-reload"

echo "==> Preparing persistent state dir..."
ssh "$PI" "sudo install -d -o daemon -g daemon /var/lib/loadcounter && sudo install -d -o jul -g jul /var/tmp/loadcounter"

echo "==> Restarting service..."
ssh "$PI" "sudo systemctl restart $SERVICE $KEYBOARD_SERVICE"

echo "==> Status:"
ssh "$PI" "sudo systemctl status $SERVICE $KEYBOARD_SERVICE --no-pager -l"

echo ""
echo "Done. Use ./logs.sh to view logs."

#!/usr/bin/env bash
set -euo pipefail

PI="jul@raspberry.local"
REMOTE_DIR="/home/jul/loadcounter"
SERVICE="loadcounter"

echo "==> Copying files to Pi..."
scp load-counter.py test-ultrasonic.sensors.py "$PI:$REMOTE_DIR/"
scp loadcounter.service "$PI:/tmp/loadcounter.service"

echo "==> Installing service unit..."
ssh "$PI" "sudo mv /tmp/loadcounter.service /etc/systemd/system/loadcounter.service && sudo systemctl daemon-reload"

echo "==> Preparing persistent state dir..."
ssh "$PI" "sudo install -d -o daemon -g daemon /var/lib/loadcounter"

echo "==> Restarting service..."
ssh "$PI" "sudo systemctl restart $SERVICE"

echo "==> Status:"
ssh "$PI" "sudo systemctl status $SERVICE --no-pager -l"

echo ""
echo "Done. Use ./logs.sh to view logs."

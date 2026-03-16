#!/usr/bin/env bash
set -euo pipefail

PI="jul@raspberry.local"
REMOTE_DIR="/home/jul/loadcounter"
SERVICE="loadcounter"

echo "==> Copying files to Pi..."
scp load-counter.py test-ultrasonic.sensors.py "$PI:$REMOTE_DIR/"

echo "==> Restarting service..."
ssh "$PI" "sudo systemctl restart $SERVICE"

echo "==> Status:"
ssh "$PI" "sudo systemctl status $SERVICE --no-pager -l"

echo ""
echo "Done. Use ./logs.sh to view logs."

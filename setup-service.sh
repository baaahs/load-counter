#!/usr/bin/env bash
set -euo pipefail

PI="jul@raspberry.local"
SERVICE="loadcounter"

echo "==> Copying service file to Pi..."
scp loadcounter.service "$PI:/tmp/$SERVICE.service"

echo "==> Installing service..."
ssh "$PI" "
    sudo mv /tmp/$SERVICE.service /etc/systemd/system/$SERVICE.service
    sudo systemctl daemon-reload
    sudo systemctl enable $SERVICE
    sudo systemctl start $SERVICE
"

echo "==> Service installed and started:"
ssh "$PI" "sudo systemctl status $SERVICE --no-pager -l"

echo ""
echo "Done! Service will start on boot."
echo "Use ./deploy.sh to push code updates."
echo "Use ./logs.sh to view logs."

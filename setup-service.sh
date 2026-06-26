#!/usr/bin/env bash
set -euo pipefail

PI="jul@raspberry.local"
SERVICE="loadcounter"
KEYBOARD_SERVICE="loadcounter-keyboard"
BLE_SERVICE="loadcounter-ble"

echo "==> Copying service files to Pi..."
scp loadcounter.service "$PI:/tmp/$SERVICE.service"
scp loadcounter-keyboard.service "$PI:/tmp/$KEYBOARD_SERVICE.service"
scp loadcounter-ble.service "$PI:/tmp/$BLE_SERVICE.service"

echo "==> Installing service..."
ssh "$PI" "
    sudo mv /tmp/$SERVICE.service /etc/systemd/system/$SERVICE.service
    sudo mv /tmp/$KEYBOARD_SERVICE.service /etc/systemd/system/$KEYBOARD_SERVICE.service
    sudo mv /tmp/$BLE_SERVICE.service /etc/systemd/system/$BLE_SERVICE.service
    sudo systemctl daemon-reload
    sudo systemctl enable $SERVICE $KEYBOARD_SERVICE $BLE_SERVICE
    sudo systemctl start $SERVICE $KEYBOARD_SERVICE $BLE_SERVICE
"

echo "==> Service installed and started:"
ssh "$PI" "sudo systemctl status $SERVICE $KEYBOARD_SERVICE $BLE_SERVICE --no-pager -l"

echo ""
echo "Done! Service will start on boot."
echo "Use ./deploy.sh to push code updates."
echo "Use ./logs.sh to view logs."

#!/usr/bin/env bash
set -euo pipefail

PI="jul@raspberry.local"
SERVICES="loadcounter loadcounter-keyboard loadcounter-ble"

usage() {
    echo "Usage: ./logs.sh [command]"
    echo ""
    echo "Commands:"
    echo "  live          Follow logs in real time (default)"
    echo "  last          Last 100 lines"
    echo "  last N        Last N lines"
    echo "  prev          Logs from previous run (before last restart)"
    echo "  today         Today's logs"
    echo "  status        Service status"
    exit 0
}

CMD="${1:-live}"

case "$CMD" in
    -h|--help|help)
        usage
        ;;
    live)
        echo "==> Following live logs (Ctrl+C to stop)..."
        ssh "$PI" "sudo journalctl -u loadcounter -u loadcounter-keyboard -u loadcounter-ble -f --no-pager"
        ;;
    last)
        N="${2:-100}"
        ssh "$PI" "sudo journalctl -u loadcounter -u loadcounter-keyboard -u loadcounter-ble -n $N --no-pager"
        ;;
    prev)
        echo "==> Logs from previous boot..."
        ssh "$PI" "sudo journalctl -u loadcounter -u loadcounter-keyboard -u loadcounter-ble -b -1 --no-pager"
        ;;
    today)
        ssh "$PI" "sudo journalctl -u loadcounter -u loadcounter-keyboard -u loadcounter-ble --since today --no-pager"
        ;;
    status)
        ssh "$PI" "sudo systemctl status $SERVICES --no-pager -l"
        ;;
    *)
        echo "Unknown command: $CMD"
        usage
        ;;
esac

#!/usr/bin/env bash
# setup_scheduler.sh
# Sets up automatic 15-minute execution via systemd user timer or crontab.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

echo "=== Vélo'v Tracker Scheduler Setup ==="
echo "Choose a scheduling method:"
echo "1) Systemd user timer (recommended on modern Raspberry Pi OS)"
echo "2) Crontab"
read -rp "Enter choice [1 or 2] (default: 1): " CHOICE
CHOICE="${CHOICE:-1}"

if [ "${CHOICE}" = "1" ]; then
    SYSTEMD_DIR="${HOME}/.config/systemd/user"
    mkdir -p "${SYSTEMD_DIR}"
    
    # Update paths in service file dynamically to match current repo path
    sed "s|/home/lincoln/Workspace/velov-tracker|${REPO_DIR}|g" \
        "${SCRIPT_DIR}/velov-tracker.service" > "${SYSTEMD_DIR}/velov-tracker.service"
    
    cp "${SCRIPT_DIR}/velov-tracker.timer" "${SYSTEMD_DIR}/velov-tracker.timer"
    
    systemctl --user daemon-reload
    systemctl --user enable --now velov-tracker.timer
    
    echo "✓ Systemd timer enabled and started!"
    echo "Check timer status with: systemctl --user list-timers"
    echo "View logs with: journalctl --user -u velov-tracker.service -f"

elif [ "${CHOICE}" = "2" ]; then
    CRON_CMD="*/15 * * * * ${SCRIPT_DIR}/collect_and_push.sh >> ${REPO_DIR}/collector.log 2>&1"
    
    # Check if already present in crontab
    if crontab -l 2>/dev/null | grep -Fq "collect_and_push.sh"; then
        echo "Crontab entry already exists."
    else
        (crontab -l 2>/dev/null || true; echo "${CRON_CMD}") | crontab -
        echo "✓ Crontab entry added successfully!"
        echo "Runs every 15 minutes. Logs will be written to ${REPO_DIR}/collector.log"
    fi
else
    echo "Invalid option. Exiting."
    exit 1
fi

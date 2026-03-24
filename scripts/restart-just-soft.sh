#!/usr/bin/env bash
# Safer than "systemctl restart": pause between stop and start (some Chromium builds
# crash if org.kde.krunner / session focus flips too fast).
set -euo pipefail
systemctl --user stop just-runner.service
# Let session clients (Chromium/Electron) settle after org.kde.krunner name is released.
sleep 3
systemctl --user start just-runner.service
echo "just-runner started"

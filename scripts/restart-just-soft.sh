#!/usr/bin/env bash
# Safer than "systemctl restart": pause between stop and start (some Chromium builds
# crash if org.kde.krunner / session focus flips too fast).
set -euo pipefail
systemctl --user stop just-runner.service
sleep 2
systemctl --user start just-runner.service
echo "just-runner started"

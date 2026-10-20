#!/bin/sh
# Installs (or reinstalls) the Mac worker as a background service that starts
# at login and restarts if it stops. Run from anywhere:
#   sh backend/worker/launchd/install.sh
# Remove it with:  sh backend/worker/launchd/install.sh --remove
set -eu

LABEL=com.workoutstrategy.worker
HERE=$(cd "$(dirname "$0")" && pwd)
BACKEND=$(cd "$HERE/../.." && pwd)
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
LOGS="$HOME/Library/Logs"
DOMAIN="gui/$(id -u)"

# Stop the running copy, if any.
launchctl bootout "$DOMAIN/$LABEL" 2>/dev/null || true

if [ "${1:-}" = "--remove" ]; then
  rm -f "$PLIST"
  echo "Worker service removed."
  exit 0
fi

UV=$(command -v uv || true)
if [ -z "$UV" ]; then
  echo "uv not found. Install it first (see context/setup.md)." >&2
  exit 1
fi
if ! grep -q '^MAC_WORKER_SECRET_KEY=..*' "$BACKEND/.env" 2>/dev/null; then
  echo "MAC_WORKER_SECRET_KEY is missing from backend/.env (see context/setup.md)." >&2
  exit 1
fi

mkdir -p "$HOME/Library/LaunchAgents" "$LOGS"
sed -e "s|__UV__|$UV|" -e "s|__BACKEND__|$BACKEND|" -e "s|__LOGS__|$LOGS|g" \
  "$HERE/$LABEL.plist.template" > "$PLIST"
launchctl bootstrap "$DOMAIN" "$PLIST"
echo "Worker service installed and started."
echo "Log: $LOGS/workout-strategy-worker.log"

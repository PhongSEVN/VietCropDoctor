#!/bin/sh
# Gateway entrypoint — starts the health-aggregator sidecar, then nginx.
set -e

# Health aggregator runs on loopback (nginx proxies /api/services → :8099)
python3 /usr/local/bin/health_aggregator.py &
AGGREGATOR_PID=$!

# Forward SIGTERM/SIGINT to the aggregator so it exits cleanly with nginx
trap 'kill "$AGGREGATOR_PID" 2>/dev/null; exit 0' TERM INT

# nginx becomes PID 1 of the container
exec nginx -g 'daemon off;'

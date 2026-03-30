#!/bin/sh
# Entrypoint: fix ownership of Docker named volumes (mounted as root),
# then drop privileges to appuser before running the main process.
set -e

chown -R appuser:appuser /app/data /app/uploads /app/logs 2>/dev/null || true
exec gosu appuser "$@"

#!/bin/sh
set -eu

gunicorn --bind 0.0.0.0:5001 --workers 2 --access-logfile - app:app &
PID_HTTP=$!

gunicorn --bind 0.0.0.0:5443 --workers 2 \
  --certfile /certs/quality.crt \
  --keyfile /certs/quality.key \
  --access-logfile - app:app &
PID_HTTPS=$!

trap 'kill $PID_HTTP $PID_HTTPS 2>/dev/null || true' INT TERM
wait $PID_HTTP $PID_HTTPS

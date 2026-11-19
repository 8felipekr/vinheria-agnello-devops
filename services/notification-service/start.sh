#!/bin/sh
set -eu

gunicorn --bind 0.0.0.0:5002 --workers 2 --access-logfile - app:app &
PID_HTTP=$!

gunicorn --bind 0.0.0.0:5444 --workers 2 \
  --certfile /certs/notification.crt \
  --keyfile /certs/notification.key \
  --access-logfile - app:app &
PID_HTTPS=$!

trap 'kill $PID_HTTP $PID_HTTPS 2>/dev/null || true' INT TERM
wait $PID_HTTP $PID_HTTPS

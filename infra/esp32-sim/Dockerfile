FROM alpine:3.20

RUN apk add --no-cache \
    busybox-extras \
    iproute2 \
    bind-tools \
    curl \
    python3 \
    py3-requests \
    ca-certificates

COPY dhcp-hook.sh /usr/local/bin/dhcp-hook.sh
COPY simulate_esp32.py /app/simulate_esp32.py
RUN chmod +x /usr/local/bin/dhcp-hook.sh /app/simulate_esp32.py

WORKDIR /app
CMD ["sh", "-c", "sleep 3 && udhcpc -i eth0 -x hostname:esp32-sensor-01 -n -q -s /usr/local/bin/dhcp-hook.sh || true; tail -f /dev/null"]

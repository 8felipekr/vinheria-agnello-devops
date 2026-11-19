FROM alpine:3.20

RUN apk add --no-cache dnsmasq bind-tools iproute2

RUN mkdir -p /var/lib/misc && touch /var/lib/misc/dnsmasq.leases

COPY dnsmasq.conf /etc/dnsmasq.conf
COPY hosts.vinheria /etc/hosts.vinheria

EXPOSE 53/udp 53/tcp 67/udp

ENTRYPOINT ["dnsmasq", "--no-daemon", "--log-facility=-"]

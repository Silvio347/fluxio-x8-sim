#!/bin/sh
# Installs the Wi-Fi fallback as a systemd service. Run as root on the board
# from the repository root, after creating /etc/fluxio/wifi-portal.env.
set -eu

repo=$(cd "$(dirname "$0")/.." && pwd)
lib=/usr/local/lib/fluxio-wifi-portal
env_file=/etc/fluxio/wifi-portal.env

if [ ! -f "$env_file" ]; then
  echo "missing $env_file (copy wifi-portal.example.env and fill it in)" >&2
  exit 1
fi
chmod 600 "$env_file"

install -d -m 755 "$lib"
rm -rf "$lib/fluxio_wifi"
cp -r "$repo/src/fluxio_wifi" "$lib/"
find "$lib" -name __pycache__ -type d -prune -exec rm -rf {} +

install -m 644 "$repo/deploy/fluxio-captive.conf" /etc/NetworkManager/dnsmasq-shared.d/fluxio-captive.conf
install -m 644 "$repo/deploy/fluxio-wifi-portal.service" /etc/systemd/system/fluxio-wifi-portal.service

systemctl daemon-reload
systemctl enable fluxio-wifi-portal.service
systemctl restart fluxio-wifi-portal.service
systemctl --no-pager --lines=5 status fluxio-wifi-portal.service

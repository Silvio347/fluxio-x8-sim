#!/bin/sh
# Removes the Wi-Fi fallback service. Run as root on the board. Leaves
# /etc/fluxio/wifi-portal.env in place.
set -u

systemctl disable --now fluxio-wifi-portal.service 2>/dev/null
nmcli con delete fluxio-ap 2>/dev/null
rm -f /etc/systemd/system/fluxio-wifi-portal.service
rm -f /etc/NetworkManager/dnsmasq-shared.d/fluxio-captive.conf
rm -rf /usr/local/lib/fluxio-wifi-portal
systemctl daemon-reload
echo "fluxio-wifi-portal removed"

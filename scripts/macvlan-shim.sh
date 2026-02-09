#!/bin/bash
# macvlan-shim.sh - Enable container-to-host communication

SHIM_NAME="macvlan-shim"
SHIM_IP="10.0.20.199"
PARENT_IF="eth0"

# Remove existing shim if present
ip link delete "$SHIM_NAME" 2>/dev/null

# Create macvlan interface
ip link add "$SHIM_NAME" link "$PARENT_IF" type macvlan mode bridge
ip addr add "${SHIM_IP}/32" dev "$SHIM_NAME"
ip link set "$SHIM_NAME" up

# Enable proxy ARP
sysctl -w net.ipv4.conf.all.proxy_arp=1 >/dev/null
sysctl -w net.ipv4.conf.eth0.proxy_arp=1 >/dev/null
sysctl -w net.ipv4.conf.macvlan-shim.proxy_arp=1 >/dev/null
sysctl -w net.ipv4.conf.all.forwarding=1 >/dev/null
sysctl -w net.ipv4.conf.eth0.forwarding=1 >/dev/null
sysctl -w net.ipv4.conf.macvlan-shim.forwarding=1 >/dev/null

# Add routes for all container IPs
ip route add 10.0.20.30/32 dev "$SHIM_NAME" 2>/dev/null   # AdGuard
ip route add 10.0.20.31/32 dev "$SHIM_NAME" 2>/dev/null   # Pi-hole
ip route add 10.0.20.60/32 dev "$SHIM_NAME" 2>/dev/null   # Homarr
ip route add 10.0.20.61/32 dev "$SHIM_NAME" 2>/dev/null   # Uptime Kuma
ip route add 10.0.20.123/32 dev "$SHIM_NAME" 2>/dev/null  # Home Assistant
ip route add 10.0.20.124/32 dev "$SHIM_NAME" 2>/dev/null  # Homebridge
ip route add 10.0.20.150/32 dev "$SHIM_NAME" 2>/dev/null  # RustDesk HBBS
ip route add 10.0.20.151/32 dev "$SHIM_NAME" 2>/dev/null  # RustDesk HBBR
ip route add 10.0.20.200/32 dev "$SHIM_NAME" 2>/dev/null  # NPM
ip route add 10.0.20.254/32 dev "$SHIM_NAME" 2>/dev/null  # Watchtower

echo "macvlan shim created: $SHIM_NAME ($SHIM_IP) with routes"
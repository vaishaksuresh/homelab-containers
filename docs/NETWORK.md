# Network Architecture

## Overview

This setup uses Docker's **macvlan** networking mode, which allows containers to appear as independent devices on your network with their own IP addresses.

## Why macvlan?

**Advantages:**
- Each container gets its own IP address
- No port conflicts (multiple containers can use port 53, 80, etc.)
- Services accessible directly from any device on the network
- Clean separation of services

**Trade-offs:**
- Containers cannot communicate with host by default (requires macvlan shim if needed)
- Slightly more complex than bridge networking

## Network Diagram

```
┌─────────────────────────────────────────────────────────┐
│ Services VLAN (10.0.20.0/24)                           │
│                                                          │
│  Gateway: 10.0.20.1 (UniFi Router)                     │
│                                                          │
│  ┌──────────────────────────────────────────────────┐  │
│  │ QNAP NAS (Host): 10.0.20.196                     │  │
│  │                                                   │  │
│  │  ┌─────────────────────────────────────────┐    │  │
│  │  │ Docker macvlan Network (eth0)           │    │  │
│  │  │                                          │    │  │
│  │  │  AdGuard:        10.0.20.30             │    │  │
│  │  │  Pi-hole:        10.0.20.31             │    │  │
│  │  │  nginx Proxy:    10.0.20.200            │    │  │
│  │  │  Syncthing:      10.0.20.50             │    │  │
│  │  │  Home Assistant: 10.0.20.123            │    │  │
│  │  │  Homebridge:     10.0.20.124            │    │  │
│  │  │  Watchtower:     10.0.20.254            │    │  │
│  │  └─────────────────────────────────────────┘    │  │
│  │                                                   │  │
│  │  Services on Host:                               │  │
│  │    QNAP UI:    :8080/:443                       │  │
│  │    Plex:       :32400                           │  │
│  │    SSH:        :1022                            │  │
│  └──────────────────────────────────────────────────┘  │
│                                                          │
└─────────────────────────────────────────────────────────┘
```

## macvlan Configuration

```yaml
networks:
  macvlan_services:
    driver: macvlan
    driver_opts:
      parent: eth0              # Physical interface to attach to
    ipam:
      config:
        - subnet: 10.0.20.0/24  # Services VLAN subnet
          gateway: 10.0.20.1     # Router gateway
```

## macvlan Shim (Optional)

By default, containers on macvlan cannot communicate with the host. If you need nginx to proxy services running on the host (like QNAP UI or Plex), you need a macvlan shim:

```bash
# Create macvlan shim interface
ip link add macvlan-shim link eth0 type macvlan mode bridge
ip addr add 10.0.20.199/32 dev macvlan-shim
ip link set macvlan-shim up
ip route add 10.0.20.0/24 dev macvlan-shim
```

Then configure nginx proxy hosts to use `10.0.20.199` for host services:
- QNAP UI: `http://10.0.20.199:8080`
- Plex: `http://10.0.20.199:32400`

### Making Shim Persistent

Add to NAS autorun:

```bash
# Create startup script
cat > /etc/init.d/macvlan-shim.sh << 'EOF'
#!/bin/bash
# Remove if exists (for idempotency)
ip link delete macvlan-shim 2>/dev/null

# Create macvlan interface
ip link add macvlan-shim link eth0 type macvlan mode bridge
ip addr add 10.0.20.199/32 dev macvlan-shim
ip link set macvlan-shim up

# Route container network through shim
ip route add 10.0.20.0/24 dev macvlan-shim
EOF

chmod +x /etc/init.d/macvlan-shim.sh

# Add to autorun
echo "/etc/init.d/macvlan-shim.sh" >> /etc/config/autorun.sh
```

## DNS Flow

1. Client queries `adguard.heb.bet`
2. DNS server (10.0.20.30) returns `10.0.20.200`
3. Client connects to nginx (10.0.20.200:443)
4. nginx proxies to AdGuard (10.0.20.30:80)
5. Response flows back through nginx with SSL

## Firewall Considerations

If using VLANs, ensure firewall rules allow:
- Default VLAN → Services VLAN (for client access)
- Services VLAN → Internet (for updates, DNS queries)
- Services VLAN → Services VLAN (container-to-container)

## Container-to-Container Communication

Containers on macvlan can communicate directly with each other:
- nginx (10.0.20.200) → AdGuard (10.0.20.30) ✅
- nginx (10.0.20.200) → Home Assistant (10.0.20.123) ✅

No special configuration needed!

## Troubleshooting Network Issues

### Test Container Connectivity

```bash
# From NAS, test container IP
ping 10.0.20.30

# From container, test another container
docker exec nginx-proxy-manager ping 10.0.20.30

# Check container has correct IP
docker inspect adguardhome | grep IPAddress
```

### Check macvlan Interface

```bash
# List Docker networks
docker network ls

# Inspect macvlan network
docker network inspect macvlan_services

# Check physical interface
ip addr show eth0
```

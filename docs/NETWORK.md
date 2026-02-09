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
│  │  │  Syncthing:      10.0.20.50             │    │  │
│  │  │  Homarr:         10.0.20.60             │    │  │
│  │  │  Uptime Kuma:    10.0.20.61             │    │  │
│  │  │  Home Assistant: 10.0.20.123            │    │  │
│  │  │  Homebridge:     10.0.20.124            │    │  │
│  │  │  Rustdesk HBBS:  10.0.20.150            │    │  │
│  │  │  Rustdesk HBBR:  10.0.20.151            │    │  │
│  │  │  nginx Proxy:    10.0.20.200            │    │  │
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

By default, containers on macvlan cannot communicate with the host. This is a fundamental limitation of macvlan networking - the host and containers are isolated at Layer 2.

**You need the shim if you want to:**
- Proxy QNAP web UI through nginx (e.g., `nas.heb.bet` → QNAP:8080)
- Proxy Plex through nginx (e.g., `plex.heb.bet` → Plex:32400)
- Have any container access services running directly on the NAS host
- Monitor host services from Uptime Kuma

**You DON'T need the shim if:**
- You only access host services directly by IP (e.g., `http://10.0.20.196:8080`)
- All your services run in containers (no host services to proxy)

### Step-by-Step Setup

**Step 1: SSH into your QNAP NAS**

```bash
ssh admin@10.0.20.196 -p 1022
```

**Step 2: Create the shim interface**

```bash
# Create macvlan shim interface attached to eth0
ip link add macvlan-shim link eth0 type macvlan mode bridge

# Assign an unused IP from your subnet (we use .199)
ip addr add 10.0.20.199/32 dev macvlan-shim

# Bring the interface up
ip link set macvlan-shim up

# Add route so containers can reach the host via this IP
ip route add 10.0.20.196/32 dev macvlan-shim
```

**Step 3: Verify it's working**

```bash
# Check the interface exists
ip addr show macvlan-shim
# Should show: macvlan-shim with inet 10.0.20.199/32

# Test from a container
docker exec nginx-proxy-manager ping -c 2 10.0.20.199
# Should succeed

# Test accessing a host service from container
docker exec nginx-proxy-manager curl -s -o /dev/null -w "%{http_code}" http://10.0.20.199:8080
# Should return 200 (or 301/302 for redirect)
```

**Step 4: Configure nginx proxy hosts**

In nginx Proxy Manager, use the shim IP for host services:
- QNAP UI: Forward to `http://10.0.20.199:8080`
- Plex: Forward to `http://10.0.20.199:32400`

### Making Shim Persistent on QNAP

The shim interface doesn't survive reboots. On QNAP, use the autorun mechanism:

**Step 1: Enable autorun (if not already enabled)**

Go to QNAP Control Panel → Hardware → General → Enable "Run user defined processes during startup"

**Step 2: Create the startup script**

```bash
# SSH into NAS
ssh admin@10.0.20.196 -p 1022

# Create the script
cat > /share/CACHEDEV1_DATA/Container/scripts/macvlan-shim.sh << 'EOF'
#!/bin/bash
# macvlan-shim.sh - Enable container-to-host communication
# This script creates a macvlan shim interface so Docker containers
# on macvlan network can communicate with services on the host.

SHIM_NAME="macvlan-shim"
SHIM_IP="10.0.20.199"
HOST_IP="10.0.20.196"
PARENT_IF="eth0"

# Remove existing shim if present (idempotent)
ip link delete "$SHIM_NAME" 2>/dev/null

# Create macvlan interface
ip link add "$SHIM_NAME" link "$PARENT_IF" type macvlan mode bridge
if [ $? -ne 0 ]; then
    echo "ERROR: Failed to create macvlan interface"
    exit 1
fi

# Assign IP address
ip addr add "${SHIM_IP}/32" dev "$SHIM_NAME"

# Bring interface up
ip link set "$SHIM_NAME" up

# Add route to host
ip route add "${HOST_IP}/32" dev "$SHIM_NAME"

echo "macvlan shim created: $SHIM_NAME ($SHIM_IP) -> $HOST_IP"
EOF

# Make it executable
chmod +x /share/CACHEDEV1_DATA/Container/scripts/macvlan-shim.sh
```

**Step 3: Add to QNAP autorun**

```bash
# Check if autorun.sh exists
ls -la /etc/config/qpkg.conf

# Add the script to autorun (QNAP-specific location)
echo "/share/CACHEDEV1_DATA/Container/scripts/macvlan-shim.sh" >> /etc/config/autorun.sh

# Verify it was added
cat /etc/config/autorun.sh
```

**Step 4: Test persistence**

```bash
# Reboot the NAS
reboot

# After reboot, SSH back in and verify
ssh admin@10.0.20.196 -p 1022
ip addr show macvlan-shim
```

### Troubleshooting the Shim

#### Problem: "RTNETLINK answers: File exists"

The interface already exists. Delete it first:
```bash
ip link delete macvlan-shim
# Then run the create commands again
```

#### Problem: Shim exists but containers can't reach host

Check the route is correct:
```bash
ip route show | grep macvlan-shim
# Should show: 10.0.20.196 dev macvlan-shim

# If missing, add it:
ip route add 10.0.20.196/32 dev macvlan-shim
```

#### Problem: "Cannot find device eth0"

Your NAS might use a different interface name:
```bash
# List all interfaces
ip link show

# Common alternatives: bond0, eth1, ens3
# Update the script to use the correct interface
```

#### Problem: Shim doesn't persist after reboot

1. Verify autorun is enabled in QNAP Control Panel
2. Check the script path is correct in `/etc/config/autorun.sh`
3. Check script has execute permissions: `chmod +x /path/to/script.sh`
4. Check for errors in script: run it manually and look for output

```bash
# Run manually to test
/share/CACHEDEV1_DATA/Container/scripts/macvlan-shim.sh

# Check QNAP system logs
cat /var/log/event.log | grep -i autorun
```

#### Problem: nginx returns 502 when proxying to host

1. Verify shim is working: `docker exec nginx-proxy-manager ping 10.0.20.199`
2. Verify host service is running: `curl http://10.0.20.196:8080` (from NAS itself)
3. Check you're using the shim IP (10.0.20.199) not the host IP (10.0.20.196) in nginx
4. Check nginx logs: `docker compose logs nginx-proxy`

#### Diagnostic commands

```bash
# Full shim status check
echo "=== Shim Interface ==="
ip addr show macvlan-shim

echo -e "\n=== Routes ==="
ip route show | grep -E "(macvlan|10.0.20.199|10.0.20.196)"

echo -e "\n=== Test from container ==="
docker exec nginx-proxy-manager ping -c 1 10.0.20.199

echo -e "\n=== Test host service ==="
docker exec nginx-proxy-manager curl -s -o /dev/null -w "HTTP %{http_code}\n" http://10.0.20.199:8080
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
- nginx (10.0.20.200) → Homarr (10.0.20.60) ✅
- nginx (10.0.20.200) → Uptime Kuma (10.0.20.61) ✅
- Rustdesk HBBS (10.0.20.150) → Rustdesk HBBR (10.0.20.151) ✅

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

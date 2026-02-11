# Homelab macvlan Setup - Complete Context Document

**Purpose:** This document contains all context needed to work on the QNAP homelab Docker infrastructure using Claude Code or Cowork. It documents the macvlan networking solution, the problems encountered, and the working configuration.

**Last Updated:** 2026-02-07  
**Status:** WORKING - macvlan shim successfully enabling host ↔ container communication

---

## Infrastructure Overview

### Hardware & Network
- **NAS:** QNAP TS-x53E "Kryptonite"
- **Network:** Services VLAN 10.0.20.0/24
- **Gateway:** 10.0.20.1 (UniFi)
- **NAS Host IP:** 10.0.20.196 (eth0), 10.0.20.40 (eth1 - keep unplugged)
- **DNS:** AdGuard at 10.0.20.30
- **Domain:** *.heb.bet resolves via AdGuard to nginx proxy at 10.0.20.200

### Container Infrastructure
- **Location:** `/share/CACHEDEV1_DATA/Container/`
- **Network Mode:** macvlan (each container gets own IP on physical network)
- **Reverse Proxy:** nginx Proxy Manager at 10.0.20.200
- **GitHub Repo:** https://github.com/vaishaksuresh/homelab-containers

### Container IPs

| Service | IP | Purpose |
|---------|-----|---------|
| AdGuard Home | 10.0.20.30 | DNS server with ad blocking |
| Pi-hole | 10.0.20.31 | Alternative DNS |
| Homarr | 10.0.20.60 | Dashboard |
| Uptime Kuma | 10.0.20.61 | Monitoring |
| Immich Server | 10.0.20.70 | Photo management |
| Home Assistant | 10.0.20.123 | Home automation |
| Homebridge | 10.0.20.124 | HomeKit bridge |
| RustDesk HBBS | 10.0.20.150 | Remote desktop signal |
| RustDesk HBBR | 10.0.20.151 | Remote desktop relay |
| nginx Proxy Manager | 10.0.20.200 | Reverse proxy |
| Watchtower | 10.0.20.254 | Auto-updates |

### Host Services (QNAP Apps)
- **QNAP Web UI:** 10.0.20.196:8080 (proxied via nas.heb.bet)
- **Plex:** 10.0.20.196:32400 (proxied via plex.heb.bet)
- **Syncthing:** 10.0.20.196:8384 (proxied via syncthing.heb.bet)

---

## The Problem

### macvlan Limitation
**By design, macvlan containers CANNOT communicate with the parent host interface.**

**What works:**
- ✅ Laptop → Container (10.0.20.200) - works fine
- ✅ Container → Container - works fine
- ✅ Laptop → NAS (10.0.20.196) - works fine

**What doesn't work without shim:**
- ❌ Container → NAS host (e.g., nginx trying to proxy Plex)
- ❌ NAS → Container

### Impact
- nginx Proxy Manager cannot reverse proxy host services (Plex, Syncthing, QNAP UI)
- Uptime Kuma cannot monitor host services
- Containers cannot call NAS APIs

---

## The Solution: macvlan Shim

### What is it?
A virtual network interface that bridges the gap between the macvlan network and the host.

### How it works
1. Create `macvlan-shim` interface on eth0
2. Assign it IP 10.0.20.199
3. Enable proxy ARP and forwarding
4. Add routes so traffic to containers goes through shim
5. nginx proxies to host services use shim IP (10.0.20.199) instead of host IP (10.0.20.196)

### Critical Discovery
**The missing pieces that weren't in original documentation:**
1. **Proxy ARP must be enabled** - allows shim to answer ARP requests
2. **Specific routes required** - can't just create shim, need routes for container IPs
3. **sysctl forwarding settings** - must enable IP forwarding on interfaces

---

## Working Configuration

### Current Implementation
Located in: `/share/CACHEDEV1_DATA/Container/docker-compose.yml`

The shim is now managed as a Docker container for portability:

```yaml
services:
  macvlan-shim:
    image: alpine:latest
    container_name: macvlan-shim
    network_mode: host
    privileged: true
    restart: unless-stopped
    command: >
      sh -c "
      ip link delete macvlan-shim 2>/dev/null || true &&
      ip link add macvlan-shim link eth0 type macvlan mode bridge &&
      ip addr add 10.0.20.199/32 dev macvlan-shim &&
      ip link set macvlan-shim up &&
      sysctl -w net.ipv4.conf.all.proxy_arp=1 &&
      sysctl -w net.ipv4.conf.eth0.proxy_arp=1 &&
      sysctl -w net.ipv4.conf.macvlan-shim.proxy_arp=1 &&
      sysctl -w net.ipv4.conf.all.forwarding=1 &&
      ip route add 10.0.20.16/28 dev macvlan-shim 2>/dev/null || true &&
      ip route add 10.0.20.48/28 dev macvlan-shim 2>/dev/null || true &&
      ip route add 10.0.20.64/26 dev macvlan-shim 2>/dev/null || true &&
      ip route add 10.0.20.144/28 dev macvlan-shim 2>/dev/null || true &&
      ip route add 10.0.20.192/28 dev macvlan-shim 2>/dev/null || true &&
      ip route add 10.0.20.240/28 dev macvlan-shim 2>/dev/null || true &&
      echo 'macvlan shim created' &&
      tail -f /dev/null
      "
```

### Route Ranges Explanation
- `10.0.20.16/28` = .16-.31 (DNS servers: AdGuard, Pi-hole)
- `10.0.20.48/28` = .48-.63 (Syncthing, Homarr, Uptime Kuma)
- `10.0.20.64/26` = .64-.127 (Immich, Home Assistant, Homebridge)
- `10.0.20.144/28` = .144-.159 (RustDesk)
- `10.0.20.192/28` = .192-.207 (nginx, future services)
- `10.0.20.240/28` = .240-.255 (Watchtower, future services)

### nginx Proxy Manager Configuration

**For containerized services:** Use container IP directly
- Example: AdGuard → `http://10.0.20.30:80`

**For host services:** Use shim IP (10.0.20.199)
- QNAP UI → `http://10.0.20.199:8080`
- Plex → `http://10.0.20.199:32400`
- Syncthing → `http://10.0.20.199:8384`

**Critical:** Do NOT use host IP (10.0.20.196) for proxying host services - it won't work!

---

## Verification Commands

### Check Shim Status
```bash
# SSH into NAS
ssh admin@10.0.20.196 -p 1022

# Verify shim interface exists
ip addr show macvlan-shim
# Should show: inet 10.0.20.199/32

# Verify routes
ip route show | grep macvlan-shim
# Should show 6 routes for container ranges

# Check proxy ARP
sysctl net.ipv4.conf.macvlan-shim.proxy_arp
# Should return: net.ipv4.conf.macvlan-shim.proxy_arp = 1
```

### Test Connectivity

```bash
# From NAS, test reaching containers
ping -c 2 10.0.20.200  # nginx
ping -c 2 10.0.20.30   # AdGuard
curl http://10.0.20.200:81  # Should return nginx UI HTML

# From NAS, test host services
curl http://10.0.20.196:8384  # Should work (Syncthing)

# From laptop, test proxied host services
curl http://syncthing.heb.bet  # Should work via nginx → shim → host
curl http://plex.heb.bet       # Should work
```

### Check Docker Containers

```bash
cd /share/CACHEDEV1_DATA/Container

# Check all containers running
docker compose ps

# Check macvlan-shim container specifically
docker logs macvlan-shim
# Should show: "macvlan shim created"

# Check any other container
docker compose logs nginx-proxy-manager --tail=50
```

---

## Common Issues & Solutions

### Issue: Containers can't reach host after NAS restart

**Symptoms:**
- nginx proxy returns 502 for host services
- `curl http://10.0.20.196:8384` fails from containers
- `ip addr show macvlan-shim` shows "Device does not exist"

**Root Cause:** Shim wasn't recreated after reboot

**Solution:**
```bash
# Restart the shim container
cd /share/CACHEDEV1_DATA/Container
docker compose restart macvlan-shim

# Verify it worked
ip addr show macvlan-shim
ping -c 2 10.0.20.200
```

### Issue: Host can't reach containers

**Symptoms:**
- `ping 10.0.20.200` fails from NAS
- `ip neigh show | grep 10.0.20.200` shows "FAILED"

**Root Cause:** Routes missing

**Solution:**
```bash
# Check if routes exist
ip route show | grep macvlan-shim

# If missing, restart shim container
docker compose restart macvlan-shim
```

### Issue: DNS resolution fails in containers

**Symptoms:**
- Containers can't resolve *.heb.bet domains
- `docker exec uptime-kuma cat /etc/resolv.conf` shows wrong DNS

**Root Cause:** Container missing DNS config

**Solution:**
Add to docker-compose.yml:
```yaml
services:
  container-name:
    dns:
      - 10.0.20.30  # AdGuard
      - 1.1.1.1     # Fallback
```

Or use YAML anchor (recommended):
```yaml
x-dns: &default-dns
  - 10.0.20.30
  - 1.1.1.1

services:
  container-name:
    dns: *default-dns
```

### Issue: eth1 interface causing routing problems

**Symptoms:**
- `ip route get 10.0.20.200` shows "dev eth1 src 10.0.20.40"
- Traffic goes out wrong interface

**Solution:**
```bash
# Physically unplug eth1 cable
# OR disable in QNAP network settings
# OR add specific routes with lower metric on eth0
```

---

## Troubleshooting Workflow

### Step 1: Verify Shim Exists
```bash
ip addr show macvlan-shim
```
**If missing:** `docker compose restart macvlan-shim`

### Step 2: Verify Routes
```bash
ip route show | grep macvlan-shim | wc -l
```
**Should return:** 6 (one per route range)  
**If wrong:** `docker compose restart macvlan-shim`

### Step 3: Verify Proxy ARP
```bash
sysctl net.ipv4.conf.macvlan-shim.proxy_arp
```
**Should return:** 1  
**If 0:** `docker compose restart macvlan-shim`

### Step 4: Test Host → Container
```bash
ping -c 2 10.0.20.200
```
**If fails:** Check routes, check ARP table with `ip neigh show`

### Step 5: Test Container → Host
```bash
# From laptop
curl http://syncthing.heb.bet
```
**If fails:** Check nginx proxy config uses 10.0.20.199, not 10.0.20.196

### Step 6: Check Logs
```bash
docker compose logs macvlan-shim
docker compose logs nginx-proxy-manager
docker compose logs uptime-kuma
```

---

## File Locations

### Primary Files
- **docker-compose.yml:** `/share/CACHEDEV1_DATA/Container/docker-compose.yml`
- **Shim script (standalone):** `/share/CACHEDEV1_DATA/Container/scripts/macvlan-shim.sh`
- **Documentation:** `/share/CACHEDEV1_DATA/Container/docs/`

### Configuration Directories
- **AdGuard:** `/share/CACHEDEV1_DATA/Container/adguardhome/`
- **nginx Proxy:** `/share/CACHEDEV1_DATA/Container/nginx-proxy-manager/`
- **Uptime Kuma:** `/share/CACHEDEV1_DATA/Container/uptime-kuma/`

### Logs
- **Container logs:** `docker compose logs <service>`
- **NAS system log:** `/var/log/` (limited on QNAP)

---

## Architecture Decisions

### Why macvlan?
- Need multiple services on same ports (DNS on port 53 for both AdGuard and Pi-hole)
- Want services directly accessible on network without port mapping
- Cleaner separation than bridge network

### Why not bridge network?
- Port conflicts (can't run two DNS servers on port 53)
- Need external network access to containers
- Bridge requires port mapping (messy for many services)

### Why not host network?
- No isolation between containers
- All containers would conflict on same ports
- Security concerns

### Why docker-compose for shim vs. startup script?
- **Portability:** Shim config is version controlled with containers
- **Self-contained:** No QNAP-specific autorun dependencies
- **Declarative:** Part of infrastructure-as-code
- **Automatic:** Starts with `docker compose up`

---

## Future Improvements

### Planned
1. ✅ DONE: Move shim to docker-compose
2. Add DNS config to all containers using YAML anchors
3. Document Tailscale subnet router setup (moved to Apple TV)
4. Set up monitoring for shim container health
5. Create backup/restore procedures for container data

### Under Consideration
1. Migrate from QNAP to bare metal K3s (removes complexity)
2. Evaluate ipvlan L2 as alternative to macvlan
3. Implement container health checks
4. Add Prometheus/Grafana monitoring stack

---

## Quick Commands Reference

### SSH Access
```bash
ssh admin@10.0.20.196 -p 1022
```

### Docker Operations
```bash
cd /share/CACHEDEV1_DATA/Container

# Start all services
docker compose up -d

# Stop all services
docker compose down

# Restart specific service
docker compose restart <service-name>

# View logs
docker compose logs -f <service-name>

# Check status
docker compose ps
```

### Network Debugging
```bash
# Check interface
ip addr show macvlan-shim

# Check routes
ip route show | grep macvlan-shim

# Check ARP
ip neigh show | grep 10.0.20

# Test connectivity
ping -c 2 10.0.20.200
curl http://10.0.20.200:81
```

### Force Shim Rebuild
```bash
cd /share/CACHEDEV1_DATA/Container
docker compose down
docker compose up -d macvlan-shim
docker compose up -d
```

---

## Context for AI Assistants

### When resuming work:
1. Always check shim status first: `ip addr show macvlan-shim`
2. Verify routes exist: `ip route show | grep macvlan-shim`
3. Test connectivity before making changes
4. All work should be in `/share/CACHEDEV1_DATA/Container/`
5. Changes to docker-compose.yml require `docker compose down && docker compose up -d`

### Common tasks:
- **Add new container:** Add to docker-compose.yml with `depends_on: macvlan-shim`, assign IP from available ranges, add DNS config
- **Debug connectivity:** Start with verification commands, check logs, verify shim/routes
- **Update container:** `docker compose pull <service> && docker compose up -d <service>`

### Never do:
- Delete `/share/CACHEDEV1_DATA/Container/` - it's the only persistent storage
- Use host IP (10.0.20.196) for nginx proxy to host services - use shim IP (10.0.20.199)
- Manually create shim outside docker-compose - it won't persist
- Run containers without DNS config - they'll use wrong DNS

---

## Success Indicators

**System is working correctly when:**
1. ✅ `ip addr show macvlan-shim` shows interface with 10.0.20.199
2. ✅ `ip route show | grep macvlan-shim` shows 6 routes
3. ✅ `ping -c 2 10.0.20.200` succeeds from NAS
4. ✅ `curl http://syncthing.heb.bet` succeeds from laptop
5. ✅ `curl http://plex.heb.bet` succeeds from laptop
6. ✅ `docker compose ps` shows all containers healthy
7. ✅ Uptime Kuma shows all services UP

---

## Last Known Working State

**Date:** 2026-02-07  
**Status:** All systems operational

**Verification:**
- macvlan-shim container running
- All 6 routes present
- Host ↔ Container bidirectional communication working
- nginx proxy successfully proxying host services (Plex, Syncthing)
- DNS resolution working (*.heb.bet domains)
- Uptime Kuma monitoring all services

**Recent Changes:**
- Moved shim from standalone script to docker-compose
- Added proxy ARP and forwarding sysctl settings
- Changed from single /32 routes to /28 and /26 CIDR ranges
- Unplugged eth1 to avoid routing conflicts

**Known Issues:**
- None currently

---

## For Claude Code / Cowork Sessions

### Suggested Workflow
1. Start session by reading this document
2. Verify system status with verification commands
3. Make changes in `/share/CACHEDEV1_DATA/Container/`
4. Test changes before committing
5. Update this document with any new findings
6. Commit changes to GitHub repo

### Permissions
- SSH user: admin
- Docker access: yes (admin in docker group)
- Can modify files in `/share/CACHEDEV1_DATA/Container/`
- Can run docker commands
- Can check network config

### Safety Rules
- Always backup before major changes: `cd /share/CACHEDEV1_DATA && tar -czf Container-backup-$(date +%Y%m%d).tar.gz Container/`
- Test connectivity after every network change
- Keep this document updated
- Document all discoveries in troubleshooting section

---

**End of Context Document**

# Troubleshooting Guide

## DNS Resolution Issues

### Problem: Can't resolve `*.heb.bet` domains

**Check DNS server in use:**
```bash
# macOS/Linux
nslookup adguard.heb.bet
# Should show Server: 10.0.20.30

# Check system DNS
scutil --dns | grep nameserver  # macOS
cat /etc/resolv.conf           # Linux
```

**Test AdGuard directly:**
```bash
nslookup adguard.heb.bet 10.0.20.30
# Should return 10.0.20.200
```

**Solutions:**

1. **Flush DNS cache:**
   ```bash
   # macOS
   sudo dscacheutil -flushcache
   sudo killall -HUP mDNSResponder
   
   # Linux
   sudo systemd-resolve --flush-caches
   
   # Windows
   ipconfig /flushdns
   ```

2. **Renew DHCP lease:**
   ```bash
   # macOS
   sudo ipconfig set en0 DHCP
   
   # Linux
   sudo dhclient -r && sudo dhclient
   ```

3. **Manually set DNS:**
   - Set primary DNS to `10.0.20.30` in network settings
   - Set secondary DNS to `1.1.1.1` as fallback

4. **Check DHCP configuration:**
   - Verify router/DHCP server is configured to give out `10.0.20.30` as primary DNS

## Container Won't Start

**Check logs:**
```bash
docker compose logs <container-name>

# Examples:
docker compose logs adguardhome
docker compose logs nginx-proxy
```

### Common Issues:

1. **Port already in use:**
   ```bash
   # Find what's using the port
   netstat -tlnp | grep :53
   
   # Stop conflicting service or change port
   ```

2. **Permission issues:**
   ```bash
   # Fix ownership (run on NAS)
   cd /share/CACHEDEV1_DATA/Container
   chown -R admin:administrators .
   chmod -R 755 ./container-name/
   ```

3. **Network issues:**
   ```bash
   # Recreate network
   docker compose down
   docker network rm macvlan_services
   docker compose up -d
   ```

4. **Volume mount issues:**
   ```bash
   # Check if directories exist
   ls -la /share/CACHEDEV1_DATA/Container/
   
   # Create missing directories
   mkdir -p adguardhome/{workdir,confdir}
   ```

## SSL Certificate Issues

### Problem: 502 Bad Gateway through nginx proxy

**Solutions:**

1. **Check backend is accessible:**
   ```bash
   curl http://10.0.20.30  # Test AdGuard directly
   curl http://10.0.20.123:8123  # Test Home Assistant
   ```

2. **Check nginx logs:**
   ```bash
   docker compose logs nginx-proxy
   ```

3. **Verify nginx proxy host configuration:**
   - Scheme: `http` (not https for backend)
   - Forward IP: Container IP (e.g., 10.0.20.30)
   - Forward Port: Service port (e.g., 80 for AdGuard)
   - Websockets: Enabled (for most services)

4. **For host services (QNAP, Plex):**
   - Setup macvlan shim (see [NETWORK.md](NETWORK.md#macvlan-shim-optional))
   - Use shim IP: `10.0.20.199`

### Problem: Certificate not valid

**Check certificate:**
```bash
# View certificate
openssl s_client -connect adguard.heb.bet:443 -showcerts

# Check expiration
curl -vI https://adguard.heb.bet
```

**Renew certificate:**
1. Access nginx Proxy Manager: http://10.0.20.200:81
2. Go to SSL Certificates
3. Click "Renew" on expired certificate

## AdGuard Not Listening on Port 53

### Problem: AdGuard UI works but DNS doesn't respond

**Test DNS:**
```bash
# Test if port 53 is listening
nslookup google.com 10.0.20.30

# Check from NAS
docker exec adguardhome netstat -tlnp | grep :53
```

**Solution:** AdGuard needs special capabilities on macvlan:

```yaml
adguard:
  cap_add:
    - NET_ADMIN
    - NET_RAW
    - NET_BIND_SERVICE
```

Update docker-compose.yml and restart:
```bash
docker compose up -d adguard
docker compose logs adguardhome
```

## Home Assistant / Homebridge Issues

### Problem: Services not accessible after moving to macvlan

**Check container IPs:**
```bash
docker inspect home-assistant | grep IPAddress
docker inspect homebridge | grep IPAddress

# Should show:
# Home Assistant: 10.0.20.123
# Homebridge: 10.0.20.124
```

**Update proxy configurations:**
- Home Assistant backend: `http://10.0.20.123:8123`
- Homebridge backend: `http://10.0.20.124:8581`

**Check firewall:**
- Ensure VLAN firewall allows access to these IPs

### Problem: Integrations stopped working

Some integrations may need reconfiguration after IP change:
1. HomeKit accessories may need to be re-added
2. Mobile apps may need server URL updated
3. API tokens may need refresh

## Performance Issues

**Check resource usage:**
```bash
# Container stats
docker stats

# Disk usage
df -h /share/CACHEDEV1_DATA/Container

# Memory usage
free -h
```

**Clean up:**
```bash
# Remove unused images
docker image prune -a

# Remove unused volumes
docker volume prune

# Remove stopped containers
docker container prune

# Full cleanup
docker system prune -a
```

## Backup/Restore Issues

### Problem: Restore fails with permission errors

**Fix permissions:**
```bash
cd /share/CACHEDEV1_DATA/Container
chown -R admin:administrators .
chmod -R 755 .

# For specific directories
chown -R 1000:1000 syncthing/
chown -R admin:administrators adguardhome/
```

### Problem: Backup fails

**Check disk space:**
```bash
df -h /share/CACHEDEV1_DATA

# Check backup directory
du -sh backups/*
```

**Manual backup:**
```bash
cd /share/CACHEDEV1_DATA/Container
tar -czf manual-backup.tar.gz \
  adguardhome/ \
  pihole/ \
  syncthing/ \
  nginx-proxy-manager/ \
  docker-compose.yml
```

## macvlan Host Communication

### Problem: nginx can't reach services on host (QNAP UI, Plex)

This is expected behavior with macvlan. Containers cannot communicate with the host by default.

**Solutions:**

1. **Setup macvlan shim** (see [NETWORK.md](NETWORK.md#macvlan-shim-optional))
2. **Access host services directly** without proxying through nginx
3. **Move services to containers** if possible

**Verify shim is working:**
```bash
# Check if shim interface exists
ip addr show macvlan-shim

# Test connectivity
ping 10.0.20.199

# From container
docker exec nginx-proxy-manager ping 10.0.20.199
```

## Network Connectivity

### Problem: Can't reach containers from other devices

**Check firewall rules:**
- Ensure inter-VLAN traffic is allowed
- Check UniFi firewall rules if using VLANs

**Test from NAS:**
```bash
# Can NAS reach containers?
ping 10.0.20.30
curl http://10.0.20.30
```

**Test from client device:**
```bash
# Can client reach containers?
ping 10.0.20.30
curl http://10.0.20.30
```

**Check routing:**
```bash
# On client device
traceroute 10.0.20.30

# Should show path through gateway
```

## Getting Help

### Before asking for help, gather:

1. **Container logs:**
   ```bash
   docker compose logs > container-logs.txt
   ```

2. **Network configuration:**
   ```bash
   docker network inspect macvlan_services > network-config.txt
   ip addr > ip-config.txt
   ```

3. **Container status:**
   ```bash
   docker compose ps > container-status.txt
   ```

4. **System info:**
   ```bash
   uname -a
   docker version
   docker compose version
   ```

### Quick diagnostic script:

```bash
#!/bin/bash
echo "=== Container Status ==="
docker compose ps

echo -e "\n=== Container IPs ==="
for container in adguardhome pihole-docker nginx-proxy-manager Syncthing home-assistant homebridge; do
    ip=$(docker inspect $container 2>/dev/null | grep '"IPAddress"' | tail -1 | cut -d'"' -f4)
    echo "$container: $ip"
done

echo -e "\n=== DNS Test ==="
nslookup adguard.heb.bet 10.0.20.30

echo -e "\n=== Connectivity Test ==="
ping -c 2 10.0.20.30
curl -I http://10.0.20.30 2>&1 | head -5
```

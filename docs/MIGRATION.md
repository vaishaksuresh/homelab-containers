# Migration Guide

## Migrating from Existing Setup

### From Docker Volumes to Bind Mounts

If you have existing Docker volumes and want to migrate to bind mounts for easier backups:

**Why migrate?**
- Easier backups (just copy directories)
- Easier to browse and edit files
- More transparent data location

**Steps:**

```bash
# 1. Stop containers
docker compose down

# 2. For each service, copy data from volume to bind mount
docker run --rm \
  -v <volume-name>:/source \
  -v $(pwd)/<service-dir>:/dest \
  alpine sh -c "cp -av /source/. /dest/"

# Example for nginx:
docker run --rm \
  -v nginx-volume:/source \
  -v $(pwd)/nginx-proxy-manager/data:/dest \
  alpine sh -c "cp -av /source/. /dest/"

# 3. Update docker-compose.yml to use bind mounts
# Replace:
#   volumes:
#     - nginx-volume:/data
# With:
#   volumes:
#     - ./nginx-proxy-manager/data:/data

# 4. Start containers with new configuration
docker compose up -d

# 5. Verify everything works
docker compose ps

# 6. Optionally remove old volumes
docker volume rm nginx-volume
```

### From Bridge/Host Network to macvlan

This migration gives each container its own IP address.

**Prerequisites:**
- Reserve IP addresses in your DHCP server for containers
- Update firewall rules if using VLANs
- Plan IP address scheme

**Steps:**

1. **Backup everything:**
   ```bash
   ./scripts/backup.sh
   ```

2. **Plan IP addresses:**
   ```
   AdGuard Home:    10.0.20.30
   Pi-hole:         10.0.20.31
   Syncthing:       10.0.20.50
   Homarr:          10.0.20.60
   Uptime Kuma:     10.0.20.61
   Home Assistant:  10.0.20.123
   Homebridge:      10.0.20.124
   Rustdesk HBBS:   10.0.20.150
   Rustdesk HBBR:   10.0.20.151
   nginx Proxy:     10.0.20.200
   Watchtower:      10.0.20.254
   ```

3. **Update docker-compose.yml:**
   
   Change from:
   ```yaml
   services:
     adguard:
       network_mode: host
       # or
       ports:
         - "53:53"
   ```
   
   To:
   ```yaml
   services:
     adguard:
       networks:
         macvlan_services:
           ipv4_address: 10.0.20.30
   
   networks:
     macvlan_services:
       driver: macvlan
       driver_opts:
         parent: eth0
       ipam:
         config:
           - subnet: 10.0.20.0/24
             gateway: 10.0.20.1
   ```

4. **Update DNS configuration:**
   - Point DHCP DNS to AdGuard: `10.0.20.30`
   - In AdGuard, add DNS rewrite: `*.heb.bet` → `10.0.20.200`

5. **Update nginx proxy hosts:**
   - Change all backend IPs to new container IPs
   - Example: AdGuard backend changes from `localhost:3000` to `10.0.20.30:3000`

6. **Start containers:**
   ```bash
   docker compose down
   docker compose up -d
   ```

7. **Verify:**
   ```bash
   # Check all containers have correct IPs
   docker compose ps
   for container in $(docker ps --format '{{.Names}}'); do
       echo "$container: $(docker inspect $container | grep '"IPAddress"' | tail -1 | cut -d'"' -f4)"
   done
   
   # Test DNS resolution
   nslookup adguard.heb.bet 10.0.20.30
   
   # Test web access
   curl https://adguard.heb.bet
   ```

### From Different VLAN/Subnet

If migrating to a new VLAN or changing subnet:

**Example: Moving from 10.0.0.0/24 to 10.0.20.0/24**

1. **Update docker-compose.yml:**
   ```yaml
   networks:
     macvlan_services:
       ipam:
         config:
           - subnet: 10.0.20.0/24  # Changed from 10.0.0.0/24
             gateway: 10.0.20.1     # Changed from 10.0.0.1
   
   services:
     adguard:
       networks:
         macvlan_services:
           ipv4_address: 10.0.20.30  # Changed from 10.0.0.30
   ```

2. **Update NAS network configuration:**
   - Assign static IP in new VLAN: `10.0.20.196`
   - Set gateway: `10.0.20.1`
   - Configure VLAN tagging if needed

3. **Update DHCP server:**
   - Point DNS to new AdGuard IP: `10.0.20.30`

4. **Update nginx proxy configurations:**
   - All backend IPs need updating to new subnet
   - Update SSL certificates if using IP-based configs

5. **Update firewall rules:**
   - Allow traffic to new VLAN subnet
   - Update inter-VLAN rules

6. **Restart everything:**
   ```bash
   docker compose down
   docker compose up -d
   ```

### From Host Network Mode

Some containers may have been using `network_mode: host`. Here's how to migrate them to macvlan:

**Before (Host mode):**
```yaml
home-assistant:
  image: ghcr.io/home-assistant/home-assistant:stable
  network_mode: host
  volumes:
    - ./home-assistant/config:/config
```

**After (macvlan):**
```yaml
home-assistant:
  image: ghcr.io/home-assistant/home-assistant:stable
  privileged: true  # May be needed for hardware access
  volumes:
    - ./home-assistant/config:/config
  networks:
    macvlan_services:
      ipv4_address: 10.0.20.123
```

**Update integrations:**
- HomeKit: May need to re-add accessories
- Mobile apps: Update server URL to new IP
- Webhooks: Update URLs in external services
- API calls: Update hardcoded IPs

## Post-Migration Checklist

- [ ] All containers running: `docker compose ps`
- [ ] Containers have correct IPs: `docker inspect <container>`
- [ ] DNS resolution works: `nslookup adguard.heb.bet 10.0.20.30`
- [ ] nginx proxy hosts updated with new IPs
- [ ] SSL certificates valid and accessible
- [ ] Services accessible via HTTPS: `curl https://adguard.heb.bet`
- [ ] Backup taken of new configuration
- [ ] Documentation updated with new IPs
- [ ] Monitoring/alerts updated with new IPs
- [ ] Mobile apps reconfigured if needed
- [ ] External webhooks/integrations updated

## Rollback Plan

If migration fails, you can quickly rollback:

```bash
# Stop new configuration
docker compose down

# Restore old docker-compose.yml
cp docker-compose.yml.backup docker-compose.yml

# Restore from backup if needed
./scripts/restore.sh /path/to/pre-migration/backup

# Start with old configuration
docker compose up -d
```

## Common Migration Issues

### Issue: Containers won't start after migration

**Solution:**
```bash
# Check logs
docker compose logs

# Recreate network
docker network rm macvlan_services
docker compose up -d
```

### Issue: DNS not resolving after migration

**Solution:**
- Flush DNS cache on all devices
- Update DHCP DNS settings
- Verify AdGuard is listening: `nslookup google.com 10.0.20.30`

### Issue: nginx 502 errors after migration

**Solution:**
- Update all proxy host backends to new IPs
- Test backend directly: `curl http://10.0.20.30`
- Check nginx logs: `docker compose logs nginx-proxy`

### Issue: SSL certificates invalid

**Solution:**
- Regenerate certificates in nginx Proxy Manager
- Ensure DNS points to nginx IP (10.0.20.200)
- Wait for DNS propagation

## Migration Timeline

**Small setup (5-7 containers):**
- Planning: 30 minutes
- Backup: 10 minutes
- Configuration updates: 20 minutes
- Testing: 30 minutes
- **Total: ~1.5 hours**

**Large setup (10+ containers):**
- Planning: 1 hour
- Backup: 20 minutes
- Configuration updates: 45 minutes
- Testing: 1 hour
- **Total: ~3 hours**

## Tips for Smooth Migration

1. **Do it during low-traffic time** (late night/early morning)
2. **Have backup ready** before starting
3. **Test on one container first** before migrating all
4. **Keep old config** until new setup is verified
5. **Update documentation** immediately after migration
6. **Notify users** of potential downtime
7. **Have rollback plan ready**

## After Migration

1. **Monitor for 24-48 hours** for any issues
2. **Check logs daily** for the first week
3. **Verify backups work** with new configuration
4. **Update external documentation** (passwords managers, wikis, etc.)
5. **Remove old volumes/configs** after confirming everything works

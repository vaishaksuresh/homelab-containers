# Backup & Restore

## Automated Backups

### Setup Cron Job

```bash
# SSH into NAS
ssh admin@10.0.20.196 -p 1022

# Edit crontab
crontab -e

# Add daily backup at 2 AM
0 2 * * * /share/CACHEDEV1_DATA/Container/scripts/backup.sh >> /var/log/container-backup.log 2>&1

# Save and exit
```

### Backup Retention

Keep last 30 days of backups:

```bash
# Add to crontab (runs daily at 3 AM)
0 3 * * * find /share/CACHEDEV1_DATA/Container/backups -type d -mtime +30 -exec rm -rf {} \;
```

## Manual Backup

```bash
cd /share/CACHEDEV1_DATA/Container
./scripts/backup.sh
```

Backups stored in: `backups/YYYYMMDD_HHMMSS/`

## What Gets Backed Up

### Bind Mounts (Full Backup)
- **AdGuard Home** configuration and data
- **Pi-hole** configuration and blocklists
- **Syncthing** configuration (not synced data)
- **Homebridge** configuration and accessories
- **Home Assistant** configuration (if using bind mount)
- **Rustdesk** HBBS and HBBR server data
- **Homarr** configs, icons, and data
- **Uptime Kuma** monitoring data

### Docker Volumes (Full Backup)
- **nginx Proxy Manager** data (proxy configurations)
- **nginx Proxy Manager** Let's Encrypt certificates
- **Home Assistant** database (if using volume)

### Configuration Files
- `docker-compose.yml`
- Backup manifest with metadata

## Backup Contents

Each backup directory contains:

```
backups/20260111_140530/
├── adguardhome.tar.gz           # AdGuard config
├── pihole.tar.gz                # Pi-hole config
├── syncthing.tar.gz             # Syncthing config
├── homebridge.tar.gz            # Homebridge config
├── home-assistant.tar.gz        # Home Assistant config
├── rustdesk-hbbs.tar.gz         # Rustdesk signal server data
├── rustdesk-hbbr.tar.gz         # Rustdesk relay server data
├── homarr.tar.gz                # Homarr dashboard config
├── uptime-kuma.tar.gz           # Uptime Kuma monitoring data
├── nginx-data-volume.tar.gz     # nginx Proxy Manager data
├── nginx-letsencrypt-volume.tar.gz  # SSL certificates
├── homeassistant-volume.tar.gz  # HA database (if using volume)
├── docker-compose.yml           # Current configuration
└── manifest.txt                 # Backup metadata
```

## Restore from Backup

### Full Restore

**WARNING: This will overwrite all current configurations!**

```bash
# SSH into NAS
ssh admin@10.0.20.196 -p 1022

cd /share/CACHEDEV1_DATA/Container

# Run restore script
./scripts/restore.sh /path/to/backup/directory

# Example:
./scripts/restore.sh /share/CACHEDEV1_DATA/Container/backups/20260111_140530
```

The script will:
1. Ask for confirmation
2. Stop all containers
3. Restore all configurations
4. Restart containers
5. Verify services

### Selective Restore

Restore individual services without affecting others:

```bash
# Stop specific container
docker compose stop adguardhome

# Extract backup for that service
cd /share/CACHEDEV1_DATA/Container
tar -xzf /path/to/backup/adguardhome.tar.gz

# Restart container
docker compose start adguardhome
```

### Restore Docker Volumes Only

```bash
# Example: Restore nginx Proxy Manager volume
docker run --rm \
  -v nginx-volume:/dest \
  -v /path/to/backup:/backup \
  alpine \
  sh -c "rm -rf /dest/* && tar -xzf /backup/nginx-data-volume.tar.gz -C /dest"

# Restart nginx
docker compose restart nginx-proxy
```

### Restore Configuration Only

If you just want to restore docker-compose.yml:

```bash
cp /path/to/backup/docker-compose.yml /share/CACHEDEV1_DATA/Container/
docker compose up -d
```

## Offsite Backup

### Option 1: Sync to External Drive

```bash
# One-time sync
rsync -av \
  /share/CACHEDEV1_DATA/Container/backups/ \
  /share/ExternalDrive/Container-Backups/

# Add to cron for automatic offsite backups
0 4 * * * rsync -av /share/CACHEDEV1_DATA/Container/backups/ /share/ExternalDrive/Container-Backups/
```

### Option 2: Use Syncthing

Configure Syncthing container to sync backups folder to another device:

1. Access Syncthing: http://10.0.20.50:8384
2. Add folder: `/share/CACHEDEV1_DATA/Container/backups`
3. Share with remote device
4. Automatic continuous backup!

### Option 3: Cloud Storage

```bash
# Install rclone
curl https://rclone.org/install.sh | sudo bash

# Configure cloud storage (e.g., Google Drive, S3)
rclone config

# Sync backups
rclone sync /share/CACHEDEV1_DATA/Container/backups remote:homelab-backups

# Add to cron
0 5 * * * rclone sync /share/CACHEDEV1_DATA/Container/backups remote:homelab-backups
```

## Disaster Recovery

### Complete System Rebuild

If you lose the NAS or need to rebuild from scratch:

1. **Fresh install QNAP**
   - Install Container Station
   - Configure network (static IP: 10.0.20.196, VLAN 20)

2. **Restore from Git**
   ```bash
   cd /share/CACHEDEV1_DATA
   git clone <your-repo-url> Container
   cd Container
   ```

3. **Create directory structure**
   ```bash
   mkdir -p adguardhome/{workdir,confdir}
   mkdir -p pihole/etc-pihole
   mkdir -p nginx-proxy-manager/{data,letsencrypt}
   mkdir -p syncthing/config
   mkdir -p home-assistant/config
   mkdir -p homebridge
   mkdir -p watchtower
   mkdir -p rustdesk/{hbbs,hbbr}
   mkdir -p homarr/{configs,icons,data}
   mkdir -p uptime-kuma
   ```

4. **Restore from backup**
   ```bash
   ./scripts/restore.sh /path/to/latest/backup
   ```

5. **Start containers**
   ```bash
   docker compose up -d
   ```

6. **Verify all services**
   ```bash
   docker compose ps
   ```

### Recovery Time Estimate

- Network configuration: **15 minutes**
- Git clone and setup: **5 minutes**
- Container restore: **30 minutes**
- Service verification: **15 minutes**
- **Total: ~1 hour**

## Testing Backups

**Test your backups regularly!**

```bash
# Create test restore location
mkdir -p /share/CACHEDEV1_DATA/backup-test

# Extract a backup
cd /share/CACHEDEV1_DATA/backup-test
tar -xzf /path/to/backup/adguardhome.tar.gz

# Verify contents
ls -la adguardhome/

# Cleanup
rm -rf /share/CACHEDEV1_DATA/backup-test
```

## Backup Best Practices

1. **Automate backups** - Set up cron jobs
2. **Test restores** - Verify backups work quarterly
3. **Multiple locations** - Keep backups on NAS + external + cloud
4. **Monitor backup jobs** - Check logs regularly
5. **Version retention** - Keep 30 days on NAS, 90 days offsite
6. **Document process** - Keep this guide updated
7. **Secure backups** - Encrypt sensitive data

## Monitoring Backups

### Check backup status:

```bash
# List recent backups
ls -lht /share/CACHEDEV1_DATA/Container/backups/ | head -10

# Check backup log
tail -50 /var/log/container-backup.log

# Verify latest backup integrity
cd /share/CACHEDEV1_DATA/Container/backups
latest=$(ls -t | head -1)
echo "Latest backup: $latest"
tar -tzf $latest/*.tar.gz | wc -l  # File count
```

### Email notifications:

```bash
# Add to backup script
BACKUP_STATUS="Success"
BACKUP_DETAILS=$(cat $BACKUP_DIR/manifest.txt)

echo "$BACKUP_DETAILS" | mail -s "Homelab Backup $BACKUP_STATUS" your@email.com
```

## What NOT to Backup

- Container images (can be pulled from Docker Hub)
- Temporary files and logs
- Syncthing synced data (backed up on other devices)
- Large media libraries (backup separately)
- Docker system files

## Quick Reference

```bash
# Backup
./scripts/backup.sh

# Restore
./scripts/restore.sh /path/to/backup

# List backups
ls -lh backups/

# Cleanup old backups (>30 days)
find backups/ -type d -mtime +30 -exec rm -rf {} \;

# Check backup size
du -sh backups/*

# Verify backup
tar -tzf backups/latest/adguardhome.tar.gz | head
```

#!/bin/bash

# Backup script for all container configurations
# Usage: ./scripts/backup.sh

set -e

BACKUP_DIR="/share/CACHEDEV1_DATA/Container/backups/$(date +%Y%m%d_%H%M%S)"
CONTAINER_DIR="/share/CACHEDEV1_DATA/Container"

echo "=== Container Backup Script ==="
echo "Backup location: $BACKUP_DIR"

# Create backup directory
mkdir -p "$BACKUP_DIR"

# Function to backup bind mounts
backup_bind_mount() {
    local service=$1
    local path=$2
    
    if [ -d "$CONTAINER_DIR/$path" ]; then
        echo "Backing up $service..."
        tar -czf "$BACKUP_DIR/${service}.tar.gz" -C "$CONTAINER_DIR" "$path"
        echo "✓ $service backed up"
    else
        echo "⚠ $service directory not found: $path"
    fi
}

# Function to backup Docker volumes
backup_docker_volume() {
    local service=$1
    local volume=$2
    
    if docker volume inspect "$volume" >/dev/null 2>&1; then
        echo "Backing up $service volume..."
        docker run --rm \
            -v $volume:/source:ro \
            -v "$BACKUP_DIR":/backup \
            alpine \
            tar -czf /backup/${service}-volume.tar.gz -C /source .
        echo "✓ $service volume backed up"
    else
        echo "⚠ Volume not found: $volume"
    fi
}

# Backup bind mounts
backup_bind_mount "adguardhome" "adguardhome"
backup_bind_mount "pihole" "pihole"
backup_bind_mount "syncthing" "syncthing"
backup_bind_mount "homebridge" "homebridge"
backup_bind_mount "home-assistant" "home-assistant"

# Backup Docker volumes (if they exist)
backup_docker_volume "nginx-data" "nginx-volume"
backup_docker_volume "nginx-letsencrypt" "letsencrypt-volume"
backup_docker_volume "homeassistant" "Homeassistant-volume"

# Backup docker-compose.yml
cp "$CONTAINER_DIR/docker-compose.yml" "$BACKUP_DIR/"

# Create manifest
cat > "$BACKUP_DIR/manifest.txt" << MANIFEST
Backup Date: $(date)
NAS IP: 10.0.20.196
Network: Services VLAN (10.0.20.0/24)

Containers Backed Up:
- AdGuard Home
- Pi-hole
- nginx Proxy Manager
- Syncthing
- Home Assistant
- Homebridge

Files:
$(ls -lh "$BACKUP_DIR")
MANIFEST

# Calculate total size
TOTAL_SIZE=$(du -sh "$BACKUP_DIR" | cut -f1)

echo ""
echo "=== Backup Complete ==="
echo "Location: $BACKUP_DIR"
echo "Total size: $TOTAL_SIZE"
echo ""
echo "To restore, see: docs/BACKUP.md"

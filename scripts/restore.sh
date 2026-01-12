#!/bin/bash

# Restore script for container configurations
# Usage: ./scripts/restore.sh /path/to/backup/directory

set -e

if [ -z "$1" ]; then
    echo "Usage: $0 <backup_directory>"
    echo "Example: $0 /share/CACHEDEV1_DATA/Container/backups/20260111"
    exit 1
fi

BACKUP_DIR="$1"
CONTAINER_DIR="/share/CACHEDEV1_DATA/Container"

echo "=== Container Restore Script ==="
echo "Restoring from: $BACKUP_DIR"
echo ""

read -p "This will overwrite existing configurations. Continue? (yes/no): " confirm
if [ "$confirm" != "yes" ]; then
    echo "Restore cancelled"
    exit 0
fi

# Stop containers
echo "Stopping containers..."
cd "$CONTAINER_DIR"
docker compose down

# Function to restore bind mounts
restore_bind_mount() {
    local service=$1
    local path=$2
    
    if [ -f "$BACKUP_DIR/${service}.tar.gz" ]; then
        echo "Restoring $service..."
        rm -rf "$CONTAINER_DIR/$path"
        mkdir -p "$CONTAINER_DIR/$path"
        tar -xzf "$BACKUP_DIR/${service}.tar.gz" -C "$CONTAINER_DIR"
        echo "✓ $service restored"
    else
        echo "⚠ Backup not found: ${service}.tar.gz"
    fi
}

# Function to restore Docker volumes
restore_docker_volume() {
    local service=$1
    local volume=$2
    
    if [ -f "$BACKUP_DIR/${service}-volume.tar.gz" ]; then
        echo "Restoring $service volume..."
        docker run --rm \
            -v $volume:/dest \
            -v "$BACKUP_DIR":/backup \
            alpine \
            sh -c "rm -rf /dest/* && tar -xzf /backup/${service}-volume.tar.gz -C /dest"
        echo "✓ $service volume restored"
    else
        echo "⚠ Volume backup not found: ${service}-volume.tar.gz"
    fi
}

# Restore bind mounts
restore_bind_mount "adguardhome" "adguardhome"
restore_bind_mount "pihole" "pihole"
restore_bind_mount "syncthing" "syncthing"
restore_bind_mount "homebridge" "homebridge"
restore_bind_mount "home-assistant" "home-assistant"

# Restore Docker volumes (if they exist)
restore_docker_volume "nginx-data" "nginx-volume"
restore_docker_volume "nginx-letsencrypt" "letsencrypt-volume"
restore_docker_volume "homeassistant" "Homeassistant-volume"

# Restore docker-compose.yml if exists
if [ -f "$BACKUP_DIR/docker-compose.yml" ]; then
    echo "Restoring docker-compose.yml..."
    cp "$BACKUP_DIR/docker-compose.yml" "$CONTAINER_DIR/"
    echo "✓ docker-compose.yml restored"
fi

echo ""
echo "=== Restore Complete ==="
echo "Starting containers..."
docker compose up -d

echo ""
echo "Verify services:"
echo "docker compose ps"

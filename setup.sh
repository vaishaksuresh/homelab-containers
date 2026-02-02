#!/bin/bash

# Initial setup script for homelab containers
# Run this after cloning the repository to create required directory structure

set -e

echo "=== Homelab Container Setup ==="
echo "Creating directory structure..."

# Create all required directories
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
mkdir -p backups

echo "✓ Directories created"

# Set proper permissions
echo "Setting permissions..."
chmod -R 755 .
echo "✓ Permissions set"

# Make scripts executable
echo "Making scripts executable..."
chmod +x scripts/*.sh
echo "✓ Scripts are executable"

echo ""
echo "=== Setup Complete ==="
echo ""
echo "Directory structure:"
ls -la

echo ""
echo "Next steps:"
echo "1. Review docker-compose.yml and adjust IPs if needed"
echo "2. Start containers: docker compose up -d"
echo "3. Check status: docker compose ps"
echo "4. Configure services via web interfaces"
echo ""
echo "Documentation available in docs/ directory"

#!/bin/bash

# Initial setup script for homelab containers
# Run this after cloning the repository to create required directory structure

set -e

# Configuration
SHIM_NAME="macvlan-shim"
SHIM_IP="10.0.20.199"
HOST_IP="10.0.20.196"
PARENT_IF="eth0"

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

# Create macvlan shim script
echo "Creating macvlan shim script..."
cat > scripts/macvlan-shim.sh << EOF
#!/bin/bash
# macvlan-shim.sh - Enable container-to-host communication
# This script creates a macvlan shim interface so Docker containers
# on macvlan network can communicate with services on the host.

SHIM_NAME="$SHIM_NAME"
SHIM_IP="$SHIM_IP"
HOST_IP="$HOST_IP"
PARENT_IF="$PARENT_IF"

# Remove existing shim if present (idempotent)
ip link delete "\$SHIM_NAME" 2>/dev/null

# Create macvlan interface
ip link add "\$SHIM_NAME" link "\$PARENT_IF" type macvlan mode bridge
if [ \$? -ne 0 ]; then
    echo "ERROR: Failed to create macvlan interface"
    exit 1
fi

# Assign IP address
ip addr add "\${SHIM_IP}/32" dev "\$SHIM_NAME"

# Bring interface up
ip link set "\$SHIM_NAME" up

# Add route to host
ip route add "\${HOST_IP}/32" dev "\$SHIM_NAME"

echo "macvlan shim created: \$SHIM_NAME (\$SHIM_IP) -> \$HOST_IP"
EOF
chmod +x scripts/macvlan-shim.sh
echo "✓ macvlan shim script created"

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
echo "Optional - Enable macvlan shim (needed to proxy host services like QNAP UI/Plex):"
echo "  sudo ./scripts/macvlan-shim.sh"
echo ""
echo "To make shim persistent on QNAP, add to autorun:"
echo "  echo \"$(pwd)/scripts/macvlan-shim.sh\" >> /etc/config/autorun.sh"
echo ""
echo "Documentation available in docs/ directory"

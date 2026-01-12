# Homelab Container Setup

Docker Compose setup for homelab services using macvlan networking on QNAP NAS.

## 🏗️ Architecture

**Network:** Services VLAN (10.0.20.0/24)  
**Network Mode:** macvlan (each container gets its own IP)  
**Gateway:** 10.0.20.1  
**NAS Host IP:** 10.0.20.196

### Container IPs

| Service | IP | Ports | Description |
|---------|------------|-------|-------------|
| AdGuard Home | 10.0.20.30 | 53, 3000, 80 | DNS server with ad blocking |
| Pi-hole | 10.0.20.31 | 53, 80 | Alternative DNS server |
| nginx Proxy Manager | 10.0.20.200 | 80, 81, 443 | Reverse proxy with SSL termination |
| Syncthing | 10.0.20.50 | 8384, 22000 | File synchronization |
| Home Assistant | 10.0.20.123 | 8123 | Home automation platform |
| Homebridge | 10.0.20.124 | 8581 | HomeKit bridge |
| Watchtower | 10.0.20.254 | - | Automatic container updates |

## 🚀 Quick Start

### Prerequisites

1. QNAP NAS with Container Station installed
2. Network configured with Services VLAN (10.0.20.0/24)
3. Static IP assigned to NAS (10.0.20.196)
4. Firewall rules allowing traffic between VLANs (if needed)

### Initial Setup

```bash
# Clone this repository
cd /share/CACHEDEV1_DATA
git clone <your-repo-url> Container
cd Container

# Create directory structure
mkdir -p adguardhome/{workdir,confdir}
mkdir -p pihole/etc-pihole
mkdir -p nginx-proxy-manager/{data,letsencrypt}
mkdir -p syncthing/config
mkdir -p home-assistant/config
mkdir -p homebridge
mkdir -p watchtower

# Start containers
docker compose up -d

# Check status
docker compose ps
```

## 📋 Configuration

### DNS Configuration

Point your DHCP server to use AdGuard as primary DNS:
- Primary DNS: `10.0.20.30` (AdGuard)
- Secondary DNS: `1.1.1.1` (Cloudflare fallback)

In AdGuard, configure DNS rewrites for internal domains:
- `*.heb.bet` → `10.0.20.200` (nginx proxy manager)

### SSL Certificates

nginx Proxy Manager handles SSL termination for all services:
1. Access nginx at http://10.0.20.200:81
2. Default credentials: `admin@example.com` / `changeme`
3. Add proxy hosts for each service
4. Request Let's Encrypt certificates for `*.heb.bet`

### Firewall Rules

If using VLANs, add firewall rule to allow Default VLAN → Services VLAN:
- Source: Default Network (VLAN 1)
- Destination: Services Network (VLAN 20)
- Action: Accept
- Protocol: All

## 🔧 Maintenance

### Backup

```bash
# Run backup script
./scripts/backup.sh

# Backups stored in: ./backups/YYYYMMDD/
```

### Update Containers

Watchtower automatically updates containers. To update manually:

```bash
docker compose pull
docker compose up -d
```

### View Logs

```bash
# All containers
docker compose logs -f

# Specific container
docker compose logs -f adguardhome
```

## 🐛 Troubleshooting

See [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) for common issues and solutions.

## 📚 Documentation

- [Network Architecture](docs/NETWORK.md)
- [Migration Guide](docs/MIGRATION.md)
- [Backup & Restore](docs/BACKUP.md)
- [Troubleshooting](docs/TROUBLESHOOTING.md)

## 🔒 Security Notes

- Change default passwords immediately
- Keep containers updated (Watchtower handles this)
- Regular backups (automated via cron)
- SSL certificates managed by nginx Proxy Manager

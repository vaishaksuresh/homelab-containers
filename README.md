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
| Syncthing | 10.0.20.50 | 8384, 22000 | File synchronization |
| Homarr | 10.0.20.60 | 7575 | Homelab dashboard |
| Uptime Kuma | 10.0.20.61 | 3001 | Uptime monitoring & status page |
| Home Assistant | 10.0.20.123 | 8123 | Home automation platform |
| Homebridge | 10.0.20.124 | 8581 | HomeKit bridge |
| Rustdesk HBBS | 10.0.20.150 | 21115-21119 | Remote desktop signal server |
| Rustdesk HBBR | 10.0.20.151 | 21116, 21117 | Remote desktop relay server |
| nginx Proxy Manager | 10.0.20.200 | 80, 81, 443 | Reverse proxy with SSL termination |
| Watchtower | 10.0.20.254 | - | Automatic container updates (Discord alerts) |

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
mkdir -p rustdesk/{hbbs,hbbr}
mkdir -p homarr/{configs,icons,data}
mkdir -p uptime-kuma

# Start containers
docker compose up -d

# Check status
docker compose ps
```

## 📋 Configuration

### DNS Configuration

Point your DHCP server at the internal resolvers only:
- Primary DNS: `10.0.20.30` (AdGuard)
- Secondary DNS: `10.0.20.31` (Pi-hole), **not** a public resolver

> ⚠️ Don't hand out `1.1.1.1` / `8.8.8.8` via DHCP. Public resolvers return NXDOMAIN for
> `*.heb.bet`, and macOS 27 goes further: when `1.1.1.1` is in the DHCP list it discovers
> Cloudflare's encrypted resolver (DDR) and silently sends **all** queries over DoH to
> `one.one.one.one`, bypassing AdGuard entirely. `dig` still works (it queries 10.0.20.30
> directly), but browsers, `curl` and `dscacheutil` fail. On each Mac, also pin the internal
> domain to AdGuard (see [TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md#macos-hebbet-fails-but-dig-works)):
>
> ```bash
> sudo mkdir -p /etc/resolver && echo "nameserver 10.0.20.30" | sudo tee /etc/resolver/heb.bet
> sudo killall -HUP mDNSResponder
> ```

In AdGuard, configure DNS rewrites for internal domains:
- `*.heb.bet` → `10.0.20.200` (nginx proxy manager)

### Secrets

No secrets are committed to this repo; they're supplied at rebuild time.
- **Where they go:** real values go in `.env` (from `.env.example`) and in files outside the
  repo, such as the NPM bootstrap secrets (see [npm-config/README.md](npm-config/README.md)).
- **Templates:** only placeholder templates (`*.example`) are committed.
- **Commit-time check:** enable it once per clone with
  `git config core.hooksPath .githooks`. It runs `scripts/check-secrets.py` on every commit.

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

# WUD Setup Instructions

## Overview

**WUD (What's Up Docker)** is the container update monitoring tool that replaces Watchtower. It provides:
- 🖥️ Web UI at `http://10.0.20.62:3000` or `wud.heb.bet`
- 📊 Dashboard showing all containers with current vs available versions
- 🔔 Discord notifications when updates available
- ⚙️ Per-container update control (auto-update or notify-only)

## Initial Setup

### 1. Create Environment File

```bash
cd /share/CACHEDEV1_DATA/Container

# Copy the example file
cp .env.example .env

# Edit with your secrets
nano .env
```

### 2. Generate WUD Password Hash

**On Linux/macOS with htpasswd:**
```bash
htpasswd -nb admin yourpassword
# Output: admin:$apr1$abc123$xyz789
# Copy everything after "admin:" and replace $ with $$
# Result: $$apr1$$abc123$$xyz789
```

**Online (if you don't have htpasswd):**
1. Go to https://hostingcanada.org/htpasswd-generator/
2. Enter username: `admin`
3. Enter your password
4. Click "Generate"
5. Copy the hash (part after the colon)
6. Replace every `$` with `$$`
7. Paste into `.env` file as `WUD_AUTH_HASH`

### 3. Get Discord Webhook

```bash
# In Discord:
1. Right-click your channel
2. Edit Channel > Integrations > Webhooks
3. Create or copy existing webhook URL
4. Paste into .env as DISCORD_WEBHOOK_URL
```

### 4. Set Other Passwords

```bash
# Edit .env and set:
- PIHOLE_PASSWORD=your_secure_password
- IMMICH_DB_PASSWORD=another_secure_password
```

### 5. Deploy

```bash
cd /share/CACHEDEV1_DATA/Container

# Create WUD data directory
mkdir -p wud

# Start WUD (and update existing containers)
docker compose up -d

# Check WUD logs
docker logs wud -f
```

## Accessing WUD

### Direct IP
```
http://10.0.20.62:3000
```

### Via nginx Proxy (Recommended)

Add proxy host in nginx Proxy Manager:
- Domain: `wud.heb.bet`
- Scheme: `http`
- Forward Hostname: `10.0.20.62`
- Forward Port: `3000`
- Enable "Websockets Support"
- Request SSL certificate

Then access: `https://wud.heb.bet`

## Understanding WUD Labels

### Auto-Update (Safe Services)
```yaml
labels:
  - wud.watch=true
  - wud.tag.include=^\d+\.\d+\.\d+$  # Semantic versions only
```
**Used for:** nginx, Uptime Kuma, Homarr, Redis

### Notify Only (Critical Services)
```yaml
labels:
  - wud.watch=true
  - wud.tag.include=^v\d+\.\d+\.\d+$
```
**Used for:** Home Assistant, AdGuard, immich-server

### Don't Monitor
```yaml
labels:
  - wud.watch=false
```
**Used for:** WUD itself, Watchtower, supporting containers

## WUD Dashboard Explained

### Container Status Colors
- 🟢 **Green**: Up to date
- 🟡 **Yellow**: Update available (notification sent)
- 🔴 **Red**: Multiple versions behind

### Columns
- **Container**: Name of the container
- **Current**: Currently running version/tag
- **Available**: Latest available version/tag
- **Registry**: Where image comes from (Docker Hub, GHCR, etc.)

### Actions
- Click container name to see details
- Click "Update" icon to manually trigger update (if configured)
- Click "Ignore" to skip an update

## Customizing Update Behavior

### Per-Container in docker-compose.yml

**Auto-update specific container:**
```yaml
  your-service:
    image: your/image:latest
    labels:
      - wud.watch=true
      - wud.tag.include=^\d+\.\d+\.\d+$
      # This will auto-update when WUD detects new version
```

**Notify but don't auto-update:**
```yaml
  your-critical-service:
    image: critical/service:latest
    labels:
      - wud.watch=true
      # No auto-update trigger = notification only
```

**Don't monitor at all:**
```yaml
  your-service:
    labels:
      - wud.watch=false
```

### Tag Filtering

**Only semantic versions (1.2.3):**
```yaml
- wud.tag.include=^\d+\.\d+\.\d+$
```

**Only major versions (1, 2, 3):**
```yaml
- wud.tag.include=^\d+$
```

**Specific pattern (e.g., date-based like 2024.1.1):**
```yaml
- wud.tag.include=^\d{4}\.\d{1,2}\.\d+$
```

**Exclude pre-releases:**
```yaml
- wud.tag.exclude=.*(beta|alpha|rc).*
```

## Troubleshooting

### WUD Not Starting
```bash
# Check logs
docker logs wud

# Common issues:
# - Invalid password hash (missing $$ escaping)
# - Docker socket permission denied (shouldn't happen with :ro)
# - Port conflict (something else using 3000)
```

### Discord Notifications Not Working
```bash
# Verify webhook URL in .env
cat .env | grep DISCORD_WEBHOOK_URL

# Test webhook manually
curl -H "Content-Type: application/json" \
  -d '{"content":"Test from homelab"}' \
  YOUR_WEBHOOK_URL

# Check WUD logs for errors
docker logs wud | grep -i discord
```

### Container Not Being Monitored
```bash
# Check if label is correct
docker inspect your-container | grep wud.watch

# Check WUD sees it
# Go to WUD UI > click container > check if it's being tracked

# Restart WUD to re-scan
docker compose restart wud
```

### Wrong Version Detected
```bash
# Some images don't follow semver
# Adjust wud.tag.include regex for that specific image

# Example: For images using "latest", "stable", "release"
- wud.tag.include=^(latest|stable|release)$
```

## Migrating from Watchtower

### Option 1: Run Both (Recommended Initially)
- Keep Watchtower running for auto-updates
- Add WUD for visibility and monitoring
- Gradually move containers to WUD as you gain confidence

### Option 2: Full Migration
```yaml
# Comment out or remove watchtower service
# watchtower:
#   ...

# Add auto-update triggers to WUD for containers you want auto-updated
# Keep notification-only for critical services
```

## Backup Before Updates

**WUD doesn't backup before updates.** For critical services:

1. **Use notification-only mode**
2. **Manually backup before updating:**
```bash
# Backup container volumes
cd /share/CACHEDEV1_DATA/Container
tar -czf backup-$(date +%Y%m%d)-service-name.tar.gz service-name/

# Then update
docker compose pull service-name
docker compose up -d service-name
```

## Security Notes

- `.env` file contains secrets - **NEVER commit to git**
- WUD reads Docker socket (read-only) - this is safe but has API access
- Enable WUD authentication (WUD_AUTH_*) if exposing publicly
- Use HTTPS via nginx proxy for external access
- Discord webhook URLs are sensitive - don't share publicly

## Resources

- **WUD Documentation:** https://getwud.github.io/wud/
- **WUD GitHub:** https://github.com/getwud/wud
- **Discord Webhooks:** https://support.discord.com/hc/en-us/articles/228383668-Intro-to-Webhooks

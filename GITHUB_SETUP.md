# Quick Start: Push to GitHub

## 1. Download Repository

Download the `homelab-containers` folder from Claude.

## 2. Initialize Git (if needed)

```bash
cd homelab-containers

# Initialize git repository
git init

# Add all files
git add .

# Create initial commit
git commit -m "Initial commit: Homelab container setup with macvlan networking"
```

## 3. Create GitHub Repository

1. Go to https://github.com/new
2. Repository name: `homelab-containers`
3. Description: "Docker Compose setup for homelab services using macvlan networking"
4. Choose: Private (recommended for homelab configs)
5. **Don't** initialize with README (we already have one)
6. Click "Create repository"

## 4. Push to GitHub

```bash
# Add remote (replace YOUR_USERNAME with your GitHub username)
git remote add origin https://github.com/YOUR_USERNAME/homelab-containers.git

# Push to GitHub
git branch -M main
git push -u origin main
```

## 5. Transfer to NAS

**Option A: Clone on NAS**
```bash
# SSH into NAS
ssh admin@10.0.20.196 -p 1022

# Clone repository
cd /share/CACHEDEV1_DATA
git clone https://github.com/YOUR_USERNAME/homelab-containers.git Container
cd Container

# Run setup script
chmod +x setup.sh
./setup.sh

# Start containers
docker compose up -d
```

**Option B: Manual transfer**
```bash
# From your laptop, rsync files to NAS
rsync -avz --progress \
  homelab-containers/ \
  admin@10.0.20.196:/share/CACHEDEV1_DATA/Container/

# SSH into NAS and start containers
ssh admin@10.0.20.196 -p 1022
cd /share/CACHEDEV1_DATA/Container
./setup.sh
docker compose up -d
```

## 6. Verify Setup

```bash
# Check containers are running
docker compose ps

# Check container IPs
docker compose ps --format "table {{.Name}}\t{{.Status}}\t{{.Ports}}"

# Test services
curl http://10.0.20.30  # AdGuard
curl http://10.0.20.200:81  # nginx Proxy Manager
```

## 7. Future Updates

```bash
# Make changes on NAS
cd /share/CACHEDEV1_DATA/Container
vim docker-compose.yml

# Commit and push
git add .
git commit -m "Update: <description of changes>"
git push

# Or pull changes from GitHub
git pull
docker compose up -d
```

## Directory Structure

After download, you'll have:

```
homelab-containers/
├── README.md              # Main documentation
├── LICENSE                # MIT License
├── .gitignore            # Git ignore rules
├── docker-compose.yml    # Container configuration
├── setup.sh              # Initial setup script
├── docs/
│   ├── NETWORK.md        # Network architecture
│   ├── TROUBLESHOOTING.md # Common issues
│   ├── BACKUP.md         # Backup procedures
│   └── MIGRATION.md      # Migration guides
├── scripts/
│   ├── backup.sh         # Backup script
│   └── restore.sh        # Restore script
└── adguardhome/
    └── .gitkeep          # Placeholder for git
```

## Tips

- **Keep sensitive data private**: Use private GitHub repo
- **Don't commit secrets**: .gitignore already excludes data directories
- **Update regularly**: Commit changes as you make them
- **Document changes**: Use meaningful commit messages
- **Test after changes**: Always verify containers still work

## Common Git Commands

```bash
# Check status
git status

# View changes
git diff

# Add specific files
git add docker-compose.yml

# Commit with message
git commit -m "Description of changes"

# Push to GitHub
git push

# Pull latest changes
git pull

# View commit history
git log --oneline

# Create a branch for testing
git checkout -b test-feature
```

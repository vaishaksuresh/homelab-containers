# Task: Enable Manual Updates in WUD for All Containers

## Context
- Location: `/share/CACHEDEV1_DATA/Container/docker-compose.yml`
- Goal: Enable manual update buttons in WUD UI for all monitored containers
- Current state: WUD is notification-only

## Required Changes

### 1. Update WUD Service

Find the `wud:` service and modify:

**Change volumes from:**
```yaml
volumes:
  - /var/run/docker.sock:/var/run/docker.sock:ro
  - ./wud:/store
```

**To:**
```yaml
volumes:
  - /var/run/docker.sock:/var/run/docker.sock  # Remove :ro
  - ./wud:/store
  - /share/CACHEDEV1_DATA/Container:/workdir:ro
working_dir: /workdir
```

**Add to environment section:**
```yaml
environment:
  # ... existing vars ...
  
  # Enable docker-compose trigger for manual updates
  - WUD_TRIGGER_DOCKERCOMPOSE_LOCAL_MODE=simple
  - WUD_TRIGGER_DOCKERCOMPOSE_LOCAL_DOCKER_COMPOSE_COMMAND=docker compose
```

### 2. Verify Container Labels

Ensure all monitored containers have:
```yaml
labels:
  - wud.watch=true
  # Do NOT add wud.trigger.docker.local=false
```

Remove any `wud.trigger.docker.local=false` labels if present.

### 3. Deploy

After making changes, run:
```bash
cd /share/CACHEDEV1_DATA/Container
docker compose up -d wud
docker logs wud -f
```

## Expected Result

- WUD UI at http://10.0.20.62:3000 shows "Update" button for each container
- Clicking button pulls new image and recreates container via docker-compose
- All containers can be manually updated through UI

## Verification

1. Access WUD UI: `http://10.0.20.62:3000`
2. Look for 🔄 Update button next to containers with available updates
3. Click button to test manual update on a non-critical container

## Notes

- Docker socket needs write access (no `:ro`)
- Working directory mount gives WUD access to docker-compose.yml
- docker-compose trigger preserves all compose configuration
- Manual updates happen instantly when button clicked

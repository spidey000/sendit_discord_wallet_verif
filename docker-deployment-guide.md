# Docker Deployment Guide - Portainer Manual Setup

## Overview

This guide covers manual Docker deployment of the Sendit Discord Bot using Portainer. This approach gives you complete control over when and how to update your containerized bot.

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Building the Docker Image](#building-the-docker-image)
3. [Exporting/Importing Images](#exportingimporting-images)
4. [Portainer Setup](#portainer-setup)
5. [Environment Configuration](#environment-configuration)
6. [Container Deployment](#container-deployment)
7. [Volume Management](#volume-management)
8. [Monitoring & Maintenance](#monitoring--maintenance)
9. [Troubleshooting](#troubleshooting)
10. [Update Procedures](#update-procedures)

---

## Prerequisites

### Local Development Machine
- Docker installed and running
- Git access to the repository
- Basic command line knowledge

### VPS/Server Requirements
- Docker installed
- Portainer installed and configured
- Minimum 2GB RAM, 2 CPU cores
- 20GB available disk space

### Required Secrets
Before deployment, ensure you have:
- Discord Bot Token
- Supabase Database URL
- JWT Secret (32+ characters)
- SSL certificates (if using HTTPS)

---

## Building the Docker Image

### 1. Clone Repository
```bash
# Clone the repository
git clone https://github.com/spidey000/sendit_discord_wallet_verif.git
cd sendit_discord_wallet_verif

# Verify Docker configuration
ls -la Dockerfile docker-compose.yml .dockerignore
```

### 2. Configure Environment Variables
Edit the `.env` file with your production secrets:

```bash
# Copy template and edit
cp .env .env.production

# Edit with your actual values
nano .env.production
```

**Required Variables:**
```env
# Discord Bot Configuration
DISCORD_TOKEN=your_actual_discord_bot_token_here

# Database Configuration (Supabase)
DATABASE_URL=postgresql://postgres.[your-project-id]:[your-password]@aws-0-us-east-2.pooler.supabase.com:6543/postgres

# JWT Secret for Wallet Verification (32+ characters)
JWT_SECRET=your_super_secure_random_32_character_string_here

# Server Configuration
PORT=8080
HOST=0.0.0.0

# SSL Configuration (Optional)
SSL_CERT_PATH=/etc/letsencrypt/live/custom_domain.app/fullchain.pem
SSL_KEY_PATH=/etc/letsencrypt/live/custom_domain.app/privkey.pem
```

### 3. Build Docker Image
```bash
# Build the image with a specific tag
docker build -t sendit-discord-bot:latest .

# Build with version tag for tracking
docker build -t sendit-discord-bot:v1.0 .

# Verify build
docker images | grep sendit-discord-bot
```

### 4. Test Image Locally (Optional)
```bash
# Test run with environment file
docker run --rm --env-file .env.production -p 8080:8080 sendit-discord-bot:latest

# Check health
curl http://localhost:8080/api/health

# Stop test container
docker stop $(docker ps -q --filter ancestor=sendit-discord-bot:latest)
```

---

## Exporting/Importing Images

### Method 1: Save/Load Image Files

#### Export Image
```bash
# Save image to tar file
docker save sendit-discord-bot:latest > sendit-bot.tar

# Compress for faster transfer
gzip sendit-bot.tar

# Verify file size
ls -lh sendit-bot.tar.gz
```

#### Transfer to Server
```bash
# Using SCP
scp sendit-bot.tar.gz user@your-server:/tmp/

# Using rsync
rsync -avz sendit-bot.tar.gz user@your-server:/tmp/

# Or upload via Portainer web interface
```

#### Import on Server
```bash
# SSH into server
ssh user@your-server

# Load image
gunzip -c /tmp/sendit-bot.tar.gz | docker load

# Verify import
docker images | grep sendit-discord-bot
```

### Method 2: Docker Registry (Alternative)

#### Push to Docker Hub
```bash
# Tag for Docker Hub
docker tag sendit-discord-bot:latest yourusername/sendit-discord-bot:latest

# Login to Docker Hub
docker login

# Push image
docker push yourusername/sendit-discord-bot:latest
```

#### Pull from Server
```bash
# On server
docker pull yourusername/sendit-discord-bot:latest
```

---

## Portainer Setup

### 1. Access Portainer Web Interface
```
https://your-server:9443
# or
http://your-server:9000
```

### 2. Create Application Stack

1. Navigate to **Stacks** in the sidebar
2. Click **Add stack**
3. Name: `sendit-discord-bot`
4. Build method: **Web editor**

### 3. Stack Configuration

Paste this docker-compose configuration:

```yaml
version: '3.8'

services:
  sendit-bot:
    image: sendit-discord-bot:latest
    container_name: sendit-bot
    restart: unless-stopped
    
    # Environment variables
    environment:
      - DISCORD_TOKEN=${DISCORD_TOKEN}
      - DATABASE_URL=${DATABASE_URL}
      - JWT_SECRET=${JWT_SECRET}
      - PORT=8080
      - HOST=0.0.0.0
      - LOG_LEVEL=INFO
      - PYTHONUNBUFFERED=1
    
    # Port mapping
    ports:
      - "8080:8080"
      - "443:443"  # For HTTPS
    
    # Volume mounts
    volumes:
      - sendit-logs:/app/logs
      - sendit-backups:/app/backups
      - sendit-config:/app/config
      # SSL certificates (if using HTTPS)
      - /etc/letsencrypt:/etc/letsencrypt:ro
    
    # Health check
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8080/api/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 60s
    
    # Resource limits
    deploy:
      resources:
        limits:
          cpus: '1.0'
          memory: 1G
        reservations:
          cpus: '0.5'
          memory: 512M
    
    # Logging
    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "3"
    
    # Security
    security_opt:
      - no-new-privileges:true
    
    # Network
    networks:
      - sendit-network

# Networks
networks:
  sendit-network:
    driver: bridge

# Volumes
volumes:
  sendit-logs:
    driver: local
  sendit-backups:
    driver: local
  sendit-config:
    driver: local
```

---

## Environment Configuration

### 1. Set Environment Variables in Portainer

In the stack configuration, scroll to **Environment variables**:

| Variable | Value | Description |
|----------|--------|-------------|
| `DISCORD_TOKEN` | `your_actual_token` | Discord bot token |
| `DATABASE_URL` | `postgresql://...` | Supabase connection string |
| `JWT_SECRET` | `32char_random_string` | JWT signing secret |
| `PORT` | `8080` | Internal container port |
| `LOG_LEVEL` | `INFO` | Logging verbosity |

### 2. Advanced Environment Variables (Optional)

| Variable | Default | Description |
|----------|---------|-------------|
| `SSL_CERT_PATH` | - | SSL certificate path |
| `SSL_KEY_PATH` | - | SSL private key path |
| `DATABASE_POOL_SIZE` | `5` | Database connection pool size |
| `WEB_SERVER_WORKERS` | `2` | Number of web server workers |
| `HEALTH_CHECK_ENABLED` | `true` | Enable health check endpoint |
| `METRICS_ENABLED` | `true` | Enable metrics collection |

---

## Container Deployment

### 1. Deploy Stack

1. Review configuration
2. Click **Deploy the stack**
3. Monitor deployment logs
4. Wait for "Healthy" status

### 2. Verify Deployment

#### Check Container Status
```bash
# Via command line
docker ps | grep sendit-bot

# Check logs
docker logs sendit-bot

# Check health
docker exec sendit-bot curl -f http://localhost:8080/api/health
```

#### Via Portainer Web Interface
1. Navigate to **Containers**
2. Find `sendit-bot` container
3. Check status indicators:
   - 🟢 Running
   - ❤️ Healthy
   - 📊 Resource usage

### 3. Test External Access

```bash
# Test from external machine
curl http://your-server-ip:8080/api/health

# Expected response
{"status":"healthy","bot_ready":true,"guilds":1}
```

---

## Volume Management

### 1. Volume Structure

| Volume | Purpose | Path |
|--------|---------|------|
| `sendit-logs` | Application logs | `/app/logs` |
| `sendit-backups` | Database backups | `/app/backups` |
| `sendit-config` | Configuration files | `/app/config` |

### 2. Backup Volumes

#### Create Volume Backup
```bash
# Create backup container
docker run --rm -v sendit-logs:/data -v $(pwd):/backup alpine tar czf /backup/logs-backup.tar.gz -C /data .

# Backup all volumes
docker run --rm \
  -v sendit-logs:/data/logs \
  -v sendit-backups:/data/backups \
  -v sendit-config:/data/config \
  -v $(pwd):/backup alpine \
  tar czf /backup/sendit-volumes-backup.tar.gz -C /data .
```

#### Restore Volume Backup
```bash
# Restore logs volume
docker run --rm -v sendit-logs:/data -v $(pwd):/backup alpine tar xzf /backup/logs-backup.tar.gz -C /data
```

### 3. Access Volume Data

```bash
# View logs
docker run --rm -v sendit-logs:/logs alpine ls -la /logs

# View backups
docker run --rm -v sendit-backups:/backups alpine ls -la /backups

# Copy files from volume
docker cp sendit-bot:/app/logs/bot.log ./bot.log
```

---

## Monitoring & Maintenance

### 1. Health Monitoring

#### Portainer Health Checks
- Green dot: Container healthy
- Yellow dot: Container unhealthy
- Red dot: Container failed

#### Manual Health Check
```bash
# Check API health
curl -f http://localhost:8080/api/health

# Check container health
docker inspect sendit-bot --format='{{.State.Health.Status}}'

# View health check logs
docker inspect sendit-bot --format='{{range .State.Health.Log}}{{.Output}}{{end}}'
```

### 2. Log Monitoring

#### View Live Logs
```bash
# Follow logs
docker logs -f sendit-bot

# Last 100 lines
docker logs --tail 100 sendit-bot

# Logs with timestamps
docker logs -t sendit-bot
```

#### Log Rotation
Configured in docker-compose.yml:
```yaml
logging:
  driver: "json-file"
  options:
    max-size: "10m"
    max-file: "3"
```

### 3. Resource Monitoring

#### Container Stats
```bash
# Real-time stats
docker stats sendit-bot

# Single snapshot
docker stats --no-stream sendit-bot
```

#### Via Portainer
1. Navigate to **Containers**
2. Click on `sendit-bot`
3. View **Stats** tab for:
   - CPU usage
   - Memory usage
   - Network I/O
   - Disk I/O

---

## Troubleshooting

### Common Issues

#### 1. Container Won't Start
```bash
# Check startup logs
docker logs sendit-bot

# Common causes:
# - Missing environment variables
# - Port conflicts
# - Image not found
# - Insufficient resources
```

**Solutions:**
- Verify environment variables
- Check port availability: `netstat -tlnp | grep 8080`
- Ensure image exists: `docker images | grep sendit`
- Check resource limits

#### 2. Health Check Failing
```bash
# Test health endpoint manually
docker exec sendit-bot curl -f http://localhost:8080/api/health

# Check if port is bound
docker exec sendit-bot netstat -tlnp | grep 8080
```

**Solutions:**
- Verify application is listening on correct port
- Check firewall rules
- Validate environment configuration

#### 3. Database Connection Issues
```bash
# Check database connectivity
docker exec sendit-bot python -c "
import os
import asyncpg
import asyncio
async def test():
    try:
        conn = await asyncpg.connect(os.environ['DATABASE_URL'])
        await conn.close()
        print('Database connection successful')
    except Exception as e:
        print(f'Database connection failed: {e}')
asyncio.run(test())
"
```

**Solutions:**
- Verify `DATABASE_URL` format
- Check database server availability
- Validate credentials

#### 4. Permission Issues
```bash
# Check file permissions
docker exec sendit-bot ls -la /app/logs /app/backups

# Fix permissions if needed
docker exec -u root sendit-bot chown -R senditbot:senditbot /app/logs /app/backups
```

### 5. Memory/CPU Issues
```bash
# Check resource usage
docker stats sendit-bot

# Increase limits in docker-compose.yml
deploy:
  resources:
    limits:
      cpus: '2.0'
      memory: 2G
```

---

## Update Procedures

### 1. Prepare New Image

```bash
# On development machine
git pull origin main
docker build -t sendit-discord-bot:v1.1 .
docker save sendit-discord-bot:v1.1 | gzip > sendit-bot-v1.1.tar.gz

# Transfer to server
scp sendit-bot-v1.1.tar.gz user@server:/tmp/
```

### 2. Load New Image

```bash
# On server
gunzip -c /tmp/sendit-bot-v1.1.tar.gz | docker load
docker tag sendit-discord-bot:v1.1 sendit-discord-bot:latest
```

### 3. Update via Portainer

#### Method 1: Recreate Container
1. Navigate to **Containers**
2. Select `sendit-bot`
3. Click **Recreate**
4. Enable **Pull latest image version**
5. Click **Recreate**

#### Method 2: Update Stack
1. Navigate to **Stacks**
2. Select `sendit-discord-bot`
3. Click **Editor**
4. Update image tag if needed
5. Click **Update the stack**

### 4. Verify Update

```bash
# Check new image is running
docker ps | grep sendit-bot

# Verify health
curl http://localhost:8080/api/health

# Check logs for startup messages
docker logs sendit-bot | tail -20
```

### 5. Rollback if Needed

```bash
# Tag previous version as latest
docker tag sendit-discord-bot:v1.0 sendit-discord-bot:latest

# Recreate container in Portainer
# (Same steps as update)
```

---

## Security Best Practices

### 1. Container Security
- ✅ Non-root user (senditbot)
- ✅ No new privileges
- ✅ Read-only root filesystem (configurable)
- ✅ Resource limits
- ✅ Security options enabled

### 2. Network Security
```bash
# Custom network isolation
networks:
  sendit-network:
    driver: bridge
    ipam:
      config:
        - subnet: 172.20.0.0/16
```

### 3. Secret Management
- Environment variables only
- No secrets in image
- Rotate secrets regularly

### 4. Image Security
```bash
# Scan image for vulnerabilities (if available)
docker scan sendit-discord-bot:latest

# Keep base image updated
# Rebuild regularly with latest Python image
```

---

## Performance Optimization

### 1. Resource Allocation
```yaml
deploy:
  resources:
    limits:
      cpus: '1.0'      # Adjust based on load
      memory: 1G       # Monitor and adjust
    reservations:
      cpus: '0.5'      # Guaranteed minimum
      memory: 512M     # Guaranteed minimum
```

### 2. Connection Pooling
Environment variables:
```env
DATABASE_POOL_SIZE=10
DATABASE_POOL_MAX_OVERFLOW=20
WEB_SERVER_WORKERS=4
```

### 3. Logging Optimization
```yaml
logging:
  driver: "json-file"
  options:
    max-size: "10m"    # Limit log file size
    max-file: "3"      # Keep 3 rotated files
```

---

## Maintenance Schedule

### Daily
- Check container health status
- Monitor resource usage
- Review error logs

### Weekly
- Backup volumes
- Check for security updates
- Review performance metrics

### Monthly
- Update base image
- Rotate secrets (if policy requires)
- Clean up old images/volumes
- Test disaster recovery

---

## Portainer Tips

### 1. Useful Portainer Features
- **Templates**: Save stack configurations for reuse
- **Webhooks**: Set up automated deployments (advanced)
- **Notifications**: Configure alerts for container events
- **Users**: Set up access controls for team members

### 2. Stack Templates
Create reusable templates in Portainer:
1. Navigate to **App Templates**
2. Click **Add App Template**
3. Save your docker-compose configuration
4. Use for future deployments

### 3. Container Console Access
1. Navigate to **Containers**
2. Click on `sendit-bot`
3. Click **Console**
4. Choose `/bin/bash` for shell access

This completes the Docker deployment guide for manual Portainer setup. The configuration provides production-ready containerization with full control over deployment timing and processes.
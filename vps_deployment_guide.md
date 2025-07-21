# VPS Deployment Guide - Sendit Discord Bot

## Overview

This guide covers complete VPS deployment for the Sendit Discord Bot with network configuration, security hardening, and production monitoring. The bot runs directly on port 8080/443 without requiring Nginx.

## Table of Contents

1. [VPS Requirements & Selection](#vps-requirements--selection)
2. [Initial Server Setup](#initial-server-setup)
3. [Security Hardening](#security-hardening)
4. [Application Deployment](#application-deployment)
5. [Network Configuration](#network-configuration)
6. [Domain & DNS Setup](#domain--dns-setup)
7. [SSL Certificate Management](#ssl-certificate-management)
8. [Production Monitoring](#production-monitoring)
9. [Maintenance & Updates](#maintenance--updates)
10. [Troubleshooting](#troubleshooting)

---

## VPS Requirements & Selection

### Minimum Specifications
- **CPU**: 2 vCPU cores
- **RAM**: 2GB (4GB recommended)
- **Storage**: 20GB SSD
- **OS**: Ubuntu 22.04 LTS or Debian 11
- **Network**: 100Mbps bandwidth
- **Location**: Close to your user base

### Recommended VPS Providers
- **DigitalOcean**: $12/month droplet
- **Linode**: $12/month instance
- **Vultr**: $12/month instance
- **Hetzner**: €4.51/month instance (cheaper option)

### Provider Selection Criteria
```bash
# Test network speed to your target region
curl -o /dev/null -s -w 'Total: %{time_total}s\n' https://discord.com/api/v10/gateway

# Check IPv6 support
ping6 google.com

# Verify port availability
nmap -p 8080,443 your-server-ip
```

---

## Initial Server Setup

### 1. Connect to VPS
```bash
# SSH into your VPS
ssh root@your-server-ip

# Or with key authentication
ssh -i ~/.ssh/your-key root@your-server-ip
```

### 2. Create Bot User
```bash
# Add dedicated user for security
adduser senditbot
usermod -aG sudo senditbot

# Switch to bot user
su - senditbot
```

### 3. System Update
```bash
# Update package lists
sudo apt update && sudo apt upgrade -y

# Install essential packages
sudo apt install -y curl wget git vim htop unzip python3 python3-pip python3-venv

# Install Python 3.10+ (if not available)
sudo apt install -y software-properties-common
sudo add-apt-repository ppa:deadsnakes/ppa
sudo apt install -y python3.10 python3.10-venv python3.10-dev
```

### 4. Configure Timezone
```bash
# Set correct timezone
sudo timedatectl set-timezone America/New_York  # Adjust as needed
timedatectl status
```

---

## Security Hardening

### 1. SSH Configuration
```bash
# Edit SSH config
sudo vim /etc/ssh/sshd_config
```

Update SSH settings:
```conf
# Disable root login
PermitRootLogin no

# Change default port (optional but recommended)
Port 2222

# Use key authentication only
PasswordAuthentication no
PubkeyAuthentication yes

# Limit login attempts
MaxAuthTries 3
LoginGraceTime 30

# Allow specific users only
AllowUsers senditbot
```

Restart SSH:
```bash
sudo systemctl restart sshd
```

### 2. Firewall Setup (UFW)
```bash
# Enable UFW firewall
sudo ufw enable

# Default policies
sudo ufw default deny incoming
sudo ufw default allow outgoing

# Essential ports
sudo ufw allow 2222/tcp  # SSH (if changed port)
sudo ufw allow 8080/tcp  # Bot HTTP
sudo ufw allow 443/tcp   # HTTPS (if using SSL)

# Optional: Rate limiting for SSH
sudo ufw limit 2222/tcp

# Check status
sudo ufw status verbose
```

### 3. Fail2Ban Setup
```bash
# Install fail2ban
sudo apt install -y fail2ban

# Configure fail2ban
sudo cp /etc/fail2ban/jail.conf /etc/fail2ban/jail.local
sudo vim /etc/fail2ban/jail.local
```

Add bot protection:
```conf
[DEFAULT]
bantime = 3600
findtime = 600
maxretry = 3

[sshd]
enabled = true
port = 2222  # Match your SSH port

[senditbot]
enabled = true
port = 8080
filter = senditbot
logpath = /home/senditbot/logs/bot.log
maxretry = 5
```

Create custom filter:
```bash
sudo vim /etc/fail2ban/filter.d/senditbot.conf
```

```conf
[Definition]
failregex = ^.* - .*Rate limit exceeded.*from <HOST>
            ^.* - .*Invalid request.*from <HOST>
            ^.* - .*Authentication failed.*from <HOST>
ignoreregex =
```

Start fail2ban:
```bash
sudo systemctl enable fail2ban
sudo systemctl start fail2ban
```

### 4. Automatic Security Updates
```bash
# Install unattended upgrades
sudo apt install -y unattended-upgrades

# Configure automatic updates
sudo dpkg-reconfigure -plow unattended-upgrades

# Edit configuration
sudo vim /etc/apt/apt.conf.d/50unattended-upgrades
```

---

## Application Deployment

### 1. Clone Repository
```bash
# Create application directory
mkdir -p ~/sendit-bot
cd ~/sendit-bot

# Clone repository
git clone https://github.com/spidey000/sendit_discord_wallet_verif.git .

# Make bot user owner
sudo chown -R senditbot:senditbot /home/senditbot/sendit-bot
```

### 2. Python Environment
```bash
# Create virtual environment
python3.10 -m venv venv

# Activate environment
source venv/bin/activate

# Upgrade pip
pip install --upgrade pip

# Install dependencies
pip install -r requirements.txt

# Verify installation
pip list | grep -E "(discord|aiohttp|asyncpg)"
```

### 3. Environment Configuration
```bash
# Create environment file
vim .env
```

Add configuration:
```env
# Discord Bot Settings
DISCORD_TOKEN=your_discord_bot_token_here
JWT_SECRET=your_super_secure_32_character_random_string

# Database Configuration
DATABASE_URL=postgresql://postgres.[project]:password@aws-0-us-east-2.pooler.supabase.com:6543/postgres

# Server Configuration
PORT=8080
HOST=0.0.0.0

# SSL Configuration (optional)
SSL_CERT_PATH=/etc/letsencrypt/live/your-domain.com/fullchain.pem
SSL_KEY_PATH=/etc/letsencrypt/live/your-domain.com/privkey.pem

# Logging
LOG_LEVEL=INFO
LOG_FILE=/home/senditbot/logs/bot.log
```

### 4. Directory Structure
```bash
# Create necessary directories
mkdir -p logs
mkdir -p backups
mkdir -p scripts

# Set permissions
chmod 755 logs backups scripts
chmod 600 .env  # Secure environment file
```

---

## Network Configuration

### 1. Port Management
```bash
# Check what's using ports
sudo netstat -tlnp | grep -E ":(8080|443|80)"
sudo lsof -i :8080

# Kill processes if needed
sudo kill -9 PID

# Test port accessibility
nc -zv localhost 8080
```

### 2. Network Interfaces
```bash
# Check network configuration
ip addr show
ip route show

# Test external connectivity
curl -4 ifconfig.me  # Get public IPv4
curl -6 ifconfig.me  # Get public IPv6

# Test DNS resolution
nslookup discord.com
dig discord.com
```

### 3. Load Balancer Configuration (Optional)
If using cloud load balancer:
```bash
# Health check endpoint
curl -X GET http://localhost:8080/api/health

# Configure upstream
upstream senditbot {
    server 127.0.0.1:8080;
    keepalive 32;
}

# Health monitoring
server {
    listen 80;
    location /health {
        access_log off;
        return 200 "healthy\n";
    }
}
```

---

## Domain & DNS Setup

### 1. Domain Configuration
```bash
# Point your domain to VPS
# A Record: custom_domain.app -> your-server-ip
# AAAA Record: custom_domain.app -> your-server-ipv6 (if available)

# Verify DNS propagation
dig custom_domain.app
nslookup custom_domain.app
```

### 2. Subdomain Setup (Optional)
```bash
# Create subdomains for organization
# A Record: api.custom_domain.app -> your-server-ip
# CNAME: bot.custom_domain.app -> custom_domain.app
```

---

## SSL Certificate Management

### 1. Let's Encrypt Setup
```bash
# Install certbot
sudo apt install -y certbot

# Stop bot temporarily for certificate generation
sudo systemctl stop senditbot

# Generate certificate
sudo certbot certonly --standalone -d custom_domain.app

# Verify certificate
sudo certbot certificates
```

### 2. Certificate Auto-Renewal
```bash
# Test renewal
sudo certbot renew --dry-run

# Setup auto-renewal cron job
sudo crontab -e
```

Add cron job:
```cron
# Renew SSL certificates at 3 AM daily
0 3 * * * /usr/bin/certbot renew --quiet --post-hook "systemctl restart senditbot"
```

### 3. SSL Configuration Update
Update `.env` file:
```env
SSL_CERT_PATH=/etc/letsencrypt/live/custom_domain.app/fullchain.pem
SSL_KEY_PATH=/etc/letsencrypt/live/custom_domain.app/privkey.pem
```

Update `config.json`:
```json
{
  "server": {
    "ssl": {
      "enabled": true,
      "cert_path": "/etc/letsencrypt/live/custom_domain.app/fullchain.pem",
      "key_path": "/etc/letsencrypt/live/custom_domain.app/privkey.pem"
    }
  }
}
```

---

## Production Service Setup

### 1. Systemd Service
```bash
# Create service file
sudo vim /etc/systemd/system/senditbot.service
```

Service configuration:
```ini
[Unit]
Description=Sendit Discord Bot
After=network.target postgresql.service
Wants=network.target

[Service]
Type=simple
User=senditbot
Group=senditbot
WorkingDirectory=/home/senditbot/sendit-bot
Environment=PATH=/home/senditbot/sendit-bot/venv/bin
ExecStart=/home/senditbot/sendit-bot/venv/bin/python main.py
ExecReload=/bin/kill -HUP $MAINPID
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal
SyslogIdentifier=senditbot

# Security settings
NoNewPrivileges=yes
PrivateTmp=yes
ProtectSystem=strict
ProtectHome=yes
ReadWritePaths=/home/senditbot/sendit-bot/logs
ReadWritePaths=/home/senditbot/sendit-bot/backups

# Resource limits
LimitNOFILE=65536
MemoryLimit=1G

[Install]
WantedBy=multi-user.target
```

### 2. Service Management
```bash
# Reload systemd
sudo systemctl daemon-reload

# Enable service
sudo systemctl enable senditbot

# Start service
sudo systemctl start senditbot

# Check status
sudo systemctl status senditbot

# View logs
sudo journalctl -u senditbot -f
sudo journalctl -u senditbot --since "1 hour ago"
```

---

## Production Monitoring

### 1. Log Management
```bash
# Setup log rotation
sudo vim /etc/logrotate.d/senditbot
```

Log rotation configuration:
```
/home/senditbot/sendit-bot/logs/*.log {
    daily
    missingok
    rotate 30
    compress
    delaycompress
    notifempty
    create 644 senditbot senditbot
    postrotate
        systemctl reload senditbot
    endscript
}
```

### 2. Health Monitoring Script
```bash
# Create monitoring script
vim ~/scripts/health-check.sh
```

```bash
#!/bin/bash

LOG_FILE="/home/senditbot/logs/health-check.log"
BOT_URL="http://localhost:8080/api/health"
DISCORD_WEBHOOK="your-discord-webhook-url"

# Check bot health
if ! curl -f -s "$BOT_URL" > /dev/null; then
    echo "$(date): Bot health check failed" >> "$LOG_FILE"
    
    # Restart bot
    sudo systemctl restart senditbot
    
    # Send Discord notification
    curl -X POST "$DISCORD_WEBHOOK" \
         -H "Content-Type: application/json" \
         -d '{"content":"🚨 Sendit Bot restarted due to health check failure"}'
else
    echo "$(date): Bot health check passed" >> "$LOG_FILE"
fi
```

Make executable and add to cron:
```bash
chmod +x ~/scripts/health-check.sh

# Add to crontab
crontab -e
```

```cron
# Health check every 5 minutes
*/5 * * * * /home/senditbot/scripts/health-check.sh
```

### 3. Resource Monitoring
```bash
# Install monitoring tools
sudo apt install -y htop iotop nethogs

# Create resource monitoring script
vim ~/scripts/resource-monitor.sh
```

```bash
#!/bin/bash

THRESHOLD_CPU=80
THRESHOLD_MEM=80
LOG_FILE="/home/senditbot/logs/resource-monitor.log"

# Get resource usage
CPU=$(top -bn1 | grep "Cpu(s)" | awk '{print $2}' | cut -d'%' -f1)
MEM=$(free | grep Mem | awk '{printf("%.1f", $3/$2 * 100.0)}')

# Check thresholds
if (( $(echo "$CPU > $THRESHOLD_CPU" | bc -l) )); then
    echo "$(date): High CPU usage: $CPU%" >> "$LOG_FILE"
fi

if (( $(echo "$MEM > $THRESHOLD_MEM" | bc -l) )); then
    echo "$(date): High memory usage: $MEM%" >> "$LOG_FILE"
fi
```

---

## Backup Strategy

### 1. Database Backup
```bash
# Create backup script
vim ~/scripts/backup-db.sh
```

```bash
#!/bin/bash

BACKUP_DIR="/home/senditbot/backups"
DATE=$(date +%Y%m%d_%H%M%S)
DB_URL="your-database-url"

# Create backup
pg_dump "$DB_URL" > "$BACKUP_DIR/db_backup_$DATE.sql"

# Compress backup
gzip "$BACKUP_DIR/db_backup_$DATE.sql"

# Keep only last 7 days
find "$BACKUP_DIR" -name "db_backup_*.sql.gz" -mtime +7 -delete

echo "$(date): Database backup completed: db_backup_$DATE.sql.gz"
```

### 2. Configuration Backup
```bash
# Backup configuration files
vim ~/scripts/backup-config.sh
```

```bash
#!/bin/bash

BACKUP_DIR="/home/senditbot/backups"
DATE=$(date +%Y%m%d_%H%M%S)

# Create config backup
tar -czf "$BACKUP_DIR/config_backup_$DATE.tar.gz" \
    /home/senditbot/sendit-bot/config/ \
    /home/senditbot/sendit-bot/.env \
    /etc/systemd/system/senditbot.service

echo "$(date): Configuration backup completed: config_backup_$DATE.tar.gz"
```

---

## Maintenance & Updates

### 1. Update Procedure
```bash
# Create update script
vim ~/scripts/update-bot.sh
```

```bash
#!/bin/bash

set -e

echo "Starting bot update..."

# Backup current version
cp -r /home/senditbot/sendit-bot /home/senditbot/sendit-bot.backup.$(date +%Y%m%d)

# Stop bot
sudo systemctl stop senditbot

# Pull latest changes
cd /home/senditbot/sendit-bot
git fetch origin
git reset --hard origin/main

# Update dependencies
source venv/bin/activate
pip install -r requirements.txt

# Run any migration scripts if needed
# python migrate.py

# Start bot
sudo systemctl start senditbot

# Verify health
sleep 10
if curl -f -s http://localhost:8080/api/health > /dev/null; then
    echo "Update completed successfully"
    rm -rf /home/senditbot/sendit-bot.backup.*
else
    echo "Update failed, rolling back..."
    sudo systemctl stop senditbot
    rm -rf /home/senditbot/sendit-bot
    mv /home/senditbot/sendit-bot.backup.$(date +%Y%m%d) /home/senditbot/sendit-bot
    sudo systemctl start senditbot
fi
```

### 2. Maintenance Schedule
```cron
# Daily backup at 2 AM
0 2 * * * /home/senditbot/scripts/backup-db.sh
30 2 * * * /home/senditbot/scripts/backup-config.sh

# Weekly system updates on Sunday at 4 AM
0 4 * * 0 sudo apt update && sudo apt upgrade -y

# Monthly log cleanup
0 1 1 * * find /home/senditbot/logs -name "*.log" -mtime +30 -delete
```

---

## Troubleshooting

### Common Issues

#### 1. Bot Won't Start
```bash
# Check service status
sudo systemctl status senditbot

# Check logs
sudo journalctl -u senditbot -n 50

# Common causes:
# - Missing environment variables
# - Port already in use
# - Database connection issues
# - Permission problems
```

#### 2. Port Access Issues
```bash
# Check if port is open
sudo netstat -tlnp | grep 8080

# Test port accessibility
telnet your-server-ip 8080

# Check firewall
sudo ufw status
sudo iptables -L

# Check fail2ban
sudo fail2ban-client status senditbot
```

#### 3. SSL Certificate Issues
```bash
# Check certificate validity
openssl x509 -in /etc/letsencrypt/live/custom_domain.app/fullchain.pem -text -noout

# Test SSL connection
openssl s_client -connect custom_domain.app:443

# Check certificate renewal
sudo certbot certificates
```

#### 4. Database Connection Issues
```bash
# Test database connection
psql "your-database-url" -c "SELECT 1;"

# Check network connectivity
ping aws-0-us-east-2.pooler.supabase.com

# Verify DNS resolution
nslookup aws-0-us-east-2.pooler.supabase.com
```

#### 5. High Resource Usage
```bash
# Monitor resources
htop
iotop
nethogs

# Check bot memory usage
ps aux | grep python
pmap -d $(pgrep -f "python main.py")

# Analyze logs for errors
grep -i "error\|exception\|failed" /home/senditbot/logs/bot.log
```

### Emergency Recovery

#### 1. Service Recovery
```bash
# Quick restart
sudo systemctl restart senditbot

# If that fails, kill all Python processes
sudo pkill -f "python main.py"
sudo systemctl start senditbot
```

#### 2. Database Recovery
```bash
# Restore from backup
gunzip -c /home/senditbot/backups/db_backup_YYYYMMDD_HHMMSS.sql.gz | psql "your-database-url"
```

#### 3. Configuration Recovery
```bash
# Restore configuration
tar -xzf /home/senditbot/backups/config_backup_YYYYMMDD_HHMMSS.tar.gz -C /
sudo systemctl daemon-reload
sudo systemctl restart senditbot
```

---

## Performance Optimization

### 1. System Tuning
```bash
# Increase file descriptors
echo "senditbot soft nofile 65536" | sudo tee -a /etc/security/limits.conf
echo "senditbot hard nofile 65536" | sudo tee -a /etc/security/limits.conf

# TCP tuning
echo "net.core.somaxconn = 1024" | sudo tee -a /etc/sysctl.conf
echo "net.ipv4.tcp_max_syn_backlog = 1024" | sudo tee -a /etc/sysctl.conf
sudo sysctl -p
```

### 2. Application Tuning
Update `main.py` for production:
```python
# Connection pool settings
DATABASE_POOL_SIZE = 10
DATABASE_POOL_MAX_OVERFLOW = 20

# Worker process settings
WEB_SERVER_WORKERS = 2
```

---

## Security Checklist

- [ ] SSH key authentication enabled, password auth disabled
- [ ] Non-standard SSH port configured
- [ ] UFW firewall properly configured
- [ ] Fail2ban monitoring active
- [ ] SSL certificates installed and auto-renewing
- [ ] Regular security updates enabled
- [ ] Log monitoring and rotation configured
- [ ] Database credentials secured in environment variables
- [ ] File permissions properly set (600 for .env)
- [ ] Non-root user running the application
- [ ] Regular backups scheduled and tested

---

## Monitoring Dashboard

### Essential Commands
```bash
# Service status
sudo systemctl status senditbot

# Real-time logs
sudo journalctl -u senditbot -f

# Resource usage
htop

# Network connections
netstat -tlnp | grep 8080

# Bot health
curl http://localhost:8080/api/health

# Disk usage
df -h

# Memory usage
free -h
```

This comprehensive guide covers all aspects of VPS deployment, from initial setup to production monitoring. Follow each section carefully and customize the configurations based on your specific requirements.

Remember to test each step in a development environment before applying to production!
# Network Handling & Security Guide - Sendit Discord Bot

## Overview

This guide focuses on advanced network configuration, security hardening, and traffic management for the Sendit Discord Bot deployment. It covers network architecture, security policies, DDoS protection, and advanced monitoring.

## Table of Contents

1. [Network Architecture](#network-architecture)
2. [Traffic Flow & Load Balancing](#traffic-flow--load-balancing)
3. [Security Policies](#security-policies)
4. [DDoS Protection](#ddos-protection)
5. [Network Monitoring](#network-monitoring)
6. [CDN Integration](#cdn-integration)
7. [Advanced Firewall Configuration](#advanced-firewall-configuration)
8. [Intrusion Detection](#intrusion-detection)
9. [Network Performance Optimization](#network-performance-optimization)
10. [Incident Response](#incident-response)

---

## Network Architecture

### 1. Production Network Topology

```
┌─────────────────────────────────────────────────────────────────┐
│                        Internet                                 │
└─────────────────────┬───────────────────────────────────────────┘
                      │
┌─────────────────────▼───────────────────────────────────────────┐
│                  Cloudflare CDN                                 │
│              (DDoS Protection + SSL)                            │
└─────────────────────┬───────────────────────────────────────────┘
                      │
┌─────────────────────▼───────────────────────────────────────────┐
│                 VPS Public IP                                   │
│            (custom_domain.app)                                  │
└─────────────────────┬───────────────────────────────────────────┘
                      │
┌─────────────────────▼───────────────────────────────────────────┐
│              UFW Firewall                                       │
│           (Port 8080/443 Only)                                  │
└─────────────────────┬───────────────────────────────────────────┘
                      │
┌─────────────────────▼───────────────────────────────────────────┐
│            Sendit Discord Bot                                   │
│         (Direct HTTP/HTTPS Server)                             │
│              Port 8080/443                                      │
└─────────────────────┬───────────────────────────────────────────┘
                      │
┌─────────────────────▼───────────────────────────────────────────┐
│              External Services                                  │
│   ┌─────────────┐  ┌─────────────┐  ┌─────────────────────────┐ │
│   │ Discord API │  │ Supabase DB │  │ Vercel Frontend         │ │
│   │             │  │             │  │ (discord-verif-webapp   │ │
│   │             │  │             │  │  .vercel.app)           │ │
│   └─────────────┘  └─────────────┘  └─────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
```

### 2. Network Security Zones

#### Public Zone
- **Exposed Services**: HTTP/HTTPS API endpoints
- **Access**: Internet-facing
- **Protection**: Firewall, rate limiting, DDoS protection

#### Management Zone
- **Exposed Services**: SSH (non-standard port)
- **Access**: Restricted IP addresses
- **Protection**: Key-based authentication, fail2ban

#### Internal Zone
- **Services**: Application processes, logging
- **Access**: Localhost only
- **Protection**: Process isolation, user permissions

---

## Traffic Flow & Load Balancing

### 1. Request Flow Analysis

```
User → Vercel Frontend → VPS Bot API → Discord/Database
                     ↘
                       Rate Limiter → Response
```

### 2. Load Balancing Strategies

#### Single VPS (Current Setup)
```nginx
# If implementing reverse proxy later
upstream senditbot_backend {
    server 127.0.0.1:8080 weight=1 max_fails=3 fail_timeout=30s;
    keepalive 32;
}

server {
    listen 443 ssl http2;
    server_name custom_domain.app;
    
    location /api/ {
        proxy_pass http://senditbot_backend;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        # Connection pooling
        proxy_http_version 1.1;
        proxy_set_header Connection "";
        
        # Timeouts
        proxy_connect_timeout 10s;
        proxy_send_timeout 30s;
        proxy_read_timeout 30s;
    }
}
```

#### Multi-VPS Setup (Future Scaling)
```yaml
# Docker Compose example for horizontal scaling
version: '3.8'
services:
  senditbot-1:
    build: .
    environment:
      - PORT=8080
      - INSTANCE_ID=1
    
  senditbot-2:
    build: .
    environment:
      - PORT=8081
      - INSTANCE_ID=2
      
  nginx:
    image: nginx:alpine
    ports:
      - "443:443"
    depends_on:
      - senditbot-1
      - senditbot-2
```

---

## Security Policies

### 1. Network Access Control Lists (ACLs)

#### UFW Advanced Rules
```bash
# Create custom chains for organized rules
sudo iptables -N SENDITBOT_INPUT
sudo iptables -N SENDITBOT_RATE_LIMIT

# Rate limiting by IP
sudo iptables -A INPUT -p tcp --dport 8080 -m state --state NEW -m recent --set --name api_access
sudo iptables -A INPUT -p tcp --dport 8080 -m state --state NEW -m recent --update --seconds 60 --hitcount 20 --name api_access -j DROP

# Geographic blocking (example)
sudo iptables -A INPUT -p tcp --dport 8080 -m geoip --src-cc CN,RU,KP -j DROP

# Application-specific rules
sudo iptables -A INPUT -p tcp --dport 8080 -m conntrack --ctstate NEW,ESTABLISHED -j ACCEPT
sudo iptables -A INPUT -p tcp --dport 443 -m conntrack --ctstate NEW,ESTABLISHED -j ACCEPT
```

#### Application-Level ACLs
```python
# In main.py - IP whitelist/blacklist
ALLOWED_IPS = {
    'vercel_ranges': [
        '76.76.19.0/24',
        '64.23.132.0/24'  # Vercel IP ranges
    ],
    'admin_ips': [
        '192.168.1.100'  # Your admin IP
    ]
}

BLOCKED_IPS = set()  # Dynamic blocking

async def ip_filter_middleware(request, handler):
    client_ip = request.remote
    
    # Check blocked IPs
    if client_ip in BLOCKED_IPS:
        raise web.HTTPForbidden(text="IP blocked")
    
    # Whitelist for admin endpoints
    if request.path.startswith('/admin/'):
        if not any(ipaddress.ip_address(client_ip) in ipaddress.ip_network(net) 
                   for net in ALLOWED_IPS['admin_ips']):
            raise web.HTTPForbidden(text="Admin access restricted")
    
    return await handler(request)
```

### 2. SSL/TLS Configuration

#### Strong SSL Configuration
```python
# In main.py - SSL context hardening
ssl_context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
ssl_context.load_cert_chain(cert_path, key_path)

# Security settings
ssl_context.minimum_version = ssl.TLSVersion.TLSv1_2
ssl_context.set_ciphers('ECDHE+AESGCM:ECDHE+CHACHA20:DHE+AESGCM:DHE+CHACHA20:!aNULL:!MD5:!DSS')
ssl_context.options |= ssl.OP_NO_SSLv2
ssl_context.options |= ssl.OP_NO_SSLv3
ssl_context.options |= ssl.OP_NO_TLSv1
ssl_context.options |= ssl.OP_NO_TLSv1_1
ssl_context.options |= ssl.OP_SINGLE_DH_USE
ssl_context.options |= ssl.OP_SINGLE_ECDH_USE
```

#### Certificate Monitoring
```bash
# SSL certificate monitoring script
#!/bin/bash

DOMAIN="custom_domain.app"
CERT_PATH="/etc/letsencrypt/live/$DOMAIN/fullchain.pem"
WEBHOOK_URL="your-discord-webhook-url"

# Check certificate expiration
EXPIRE_DATE=$(openssl x509 -enddate -noout -in "$CERT_PATH" | cut -d= -f2)
EXPIRE_TIMESTAMP=$(date -d "$EXPIRE_DATE" +%s)
CURRENT_TIMESTAMP=$(date +%s)
DAYS_UNTIL_EXPIRE=$(( (EXPIRE_TIMESTAMP - CURRENT_TIMESTAMP) / 86400 ))

# Alert if expiring within 7 days
if [ $DAYS_UNTIL_EXPIRE -lt 7 ]; then
    curl -X POST "$WEBHOOK_URL" \
         -H "Content-Type: application/json" \
         -d "{\"content\":\"⚠️ SSL certificate for $DOMAIN expires in $DAYS_UNTIL_EXPIRE days\"}"
fi
```

---

## DDoS Protection

### 1. Rate Limiting Implementation

#### Application-Level Rate Limiting
```python
import asyncio
from collections import defaultdict, deque
import time

class AdvancedRateLimiter:
    def __init__(self):
        self.requests = defaultdict(deque)
        self.blocked_ips = {}
        self.cleanup_task = None
        
    async def is_rate_limited(self, ip: str) -> bool:
        now = time.time()
        
        # Check if IP is temporarily blocked
        if ip in self.blocked_ips:
            if now < self.blocked_ips[ip]:
                return True
            else:
                del self.blocked_ips[ip]
        
        # Clean old requests
        while self.requests[ip] and self.requests[ip][0] < now - 60:
            self.requests[ip].popleft()
        
        # Check rate limit
        if len(self.requests[ip]) >= 20:  # 20 requests per minute
            # Block IP for 15 minutes
            self.blocked_ips[ip] = now + 900
            return True
        
        self.requests[ip].append(now)
        return False
    
    async def cleanup_old_entries(self):
        """Periodic cleanup of old entries"""
        while True:
            await asyncio.sleep(300)  # Clean every 5 minutes
            now = time.time()
            
            # Clean request history
            for ip in list(self.requests.keys()):
                while self.requests[ip] and self.requests[ip][0] < now - 60:
                    self.requests[ip].popleft()
                
                if not self.requests[ip]:
                    del self.requests[ip]
            
            # Clean expired blocks
            expired_blocks = [ip for ip, expire_time in self.blocked_ips.items() 
                             if now >= expire_time]
            for ip in expired_blocks:
                del self.blocked_ips[ip]

# Usage in middleware
rate_limiter = AdvancedRateLimiter()

async def rate_limit_middleware(request, handler):
    client_ip = get_client_ip(request)
    
    if await rate_limiter.is_rate_limited(client_ip):
        return web.json_response(
            {"error": "Rate limit exceeded"}, 
            status=429,
            headers={"Retry-After": "900"}
        )
    
    return await handler(request)
```

#### System-Level DDoS Protection
```bash
# Advanced iptables rules for DDoS protection
#!/bin/bash

# Create custom chains
iptables -N DDOS_PROTECT
iptables -N RATE_LIMIT
iptables -N PORT_SCAN_DETECT

# SYN flood protection
iptables -A DDOS_PROTECT -p tcp --syn -m limit --limit 2/s --limit-burst 6 -j RETURN
iptables -A DDOS_PROTECT -p tcp --syn -j DROP

# Connection limit per IP
iptables -A DDOS_PROTECT -p tcp --dport 8080 -m connlimit --connlimit-above 20 -j DROP

# Rate limiting
iptables -A RATE_LIMIT -m hashlimit --hashlimit-mode srcip --hashlimit-name api_rate \
         --hashlimit 10/min --hashlimit-burst 5 --hashlimit-htable-expire 300000 -j RETURN
iptables -A RATE_LIMIT -j DROP

# Port scan detection
iptables -A PORT_SCAN_DETECT -p tcp --tcp-flags SYN,ACK,FIN,RST RST \
         -m limit --limit 1/s --limit-burst 2 -j RETURN
iptables -A PORT_SCAN_DETECT -p tcp --tcp-flags SYN,ACK,FIN,RST RST -j DROP

# Apply chains
iptables -A INPUT -p tcp --dport 8080 -j DDOS_PROTECT
iptables -A INPUT -p tcp --dport 8080 -j RATE_LIMIT
iptables -A INPUT -j PORT_SCAN_DETECT
```

### 2. Cloudflare Integration

#### Cloudflare Configuration
```bash
# DNS setup for Cloudflare protection
# A Record: custom_domain.app -> your-server-ip (Orange Cloud ON)

# Cloudflare rules (via dashboard or API)
curl -X POST "https://api.cloudflare.com/client/v4/zones/{zone_id}/firewall/rules" \
     -H "Authorization: Bearer {api_token}" \
     -H "Content-Type: application/json" \
     --data '{
       "filter": {
         "expression": "(http.request.uri.path matches \"^/api/.*\" and cf.threat_score gt 14)"
       },
       "action": "challenge"
     }'
```

---

## Network Monitoring

### 1. Real-Time Traffic Monitoring

#### Network Traffic Analysis Script
```python
#!/usr/bin/env python3
import psutil
import time
import json
from datetime import datetime

class NetworkMonitor:
    def __init__(self):
        self.baseline = self.get_network_stats()
        
    def get_network_stats(self):
        stats = psutil.net_io_counters()
        return {
            'bytes_sent': stats.bytes_sent,
            'bytes_recv': stats.bytes_recv,
            'packets_sent': stats.packets_sent,
            'packets_recv': stats.packets_recv,
            'timestamp': time.time()
        }
    
    def detect_anomalies(self, current_stats, threshold_mbps=10):
        time_diff = current_stats['timestamp'] - self.baseline['timestamp']
        
        bytes_sent_rate = (current_stats['bytes_sent'] - self.baseline['bytes_sent']) / time_diff
        bytes_recv_rate = (current_stats['bytes_recv'] - self.baseline['bytes_recv']) / time_diff
        
        # Convert to Mbps
        sent_mbps = bytes_sent_rate * 8 / 1024 / 1024
        recv_mbps = bytes_recv_rate * 8 / 1024 / 1024
        
        anomalies = []
        if sent_mbps > threshold_mbps:
            anomalies.append(f"High outbound traffic: {sent_mbps:.2f} Mbps")
        if recv_mbps > threshold_mbps:
            anomalies.append(f"High inbound traffic: {recv_mbps:.2f} Mbps")
            
        return anomalies

    def log_stats(self, stats, anomalies):
        log_entry = {
            'timestamp': datetime.now().isoformat(),
            'stats': stats,
            'anomalies': anomalies
        }
        
        with open('/home/senditbot/logs/network-monitor.log', 'a') as f:
            f.write(json.dumps(log_entry) + '\n')

# Usage
monitor = NetworkMonitor()
while True:
    current = monitor.get_network_stats()
    anomalies = monitor.detect_anomalies(current)
    
    if anomalies:
        monitor.log_stats(current, anomalies)
        # Send alert if needed
        
    monitor.baseline = current
    time.sleep(60)
```

#### Network Connection Monitoring
```bash
#!/bin/bash

# Monitor active connections
netstat -tuln | grep -E ":(8080|443)" > /tmp/connections.txt

# Count connections per IP
netstat -tun | awk '{print $5}' | cut -d: -f1 | sort | uniq -c | sort -nr | head -10

# Monitor for suspicious patterns
ss -tuln state established sport = :8080 | wc -l
```

### 2. Performance Metrics Collection

#### Metrics Collection Script
```python
import asyncio
import aiohttp
import time
import json
from datetime import datetime

class PerformanceMonitor:
    def __init__(self, bot_url="http://localhost:8080"):
        self.bot_url = bot_url
        
    async def collect_metrics(self):
        metrics = {
            'timestamp': datetime.now().isoformat(),
            'response_times': {},
            'status_codes': {},
            'errors': []
        }
        
        # Test health endpoint
        try:
            start_time = time.time()
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{self.bot_url}/api/health") as response:
                    response_time = time.time() - start_time
                    metrics['response_times']['health'] = response_time
                    metrics['status_codes']['health'] = response.status
                    
                    if response.status != 200:
                        metrics['errors'].append(f"Health check failed: {response.status}")
                        
        except Exception as e:
            metrics['errors'].append(f"Health check error: {str(e)}")
        
        # Test API endpoint with dummy data
        try:
            start_time = time.time()
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.bot_url}/api/confirm",
                    json={'test': 'data'}
                ) as response:
                    response_time = time.time() - start_time
                    metrics['response_times']['confirm'] = response_time
                    metrics['status_codes']['confirm'] = response.status
                    
        except Exception as e:
            metrics['errors'].append(f"API test error: {str(e)}")
        
        return metrics
    
    async def save_metrics(self, metrics):
        with open('/home/senditbot/logs/performance-metrics.log', 'a') as f:
            f.write(json.dumps(metrics) + '\n')
    
    async def alert_on_issues(self, metrics):
        # Alert if response time > 5 seconds
        for endpoint, response_time in metrics['response_times'].items():
            if response_time > 5.0:
                await self.send_alert(f"Slow response from {endpoint}: {response_time:.2f}s")
        
        # Alert on errors
        if metrics['errors']:
            await self.send_alert(f"Errors detected: {', '.join(metrics['errors'])}")
    
    async def send_alert(self, message):
        # Implement Discord webhook notification
        webhook_url = "your-discord-webhook-url"
        payload = {"content": f"🚨 Performance Alert: {message}"}
        
        try:
            async with aiohttp.ClientSession() as session:
                await session.post(webhook_url, json=payload)
        except Exception as e:
            print(f"Failed to send alert: {e}")

# Usage
async def main():
    monitor = PerformanceMonitor()
    
    while True:
        metrics = await monitor.collect_metrics()
        await monitor.save_metrics(metrics)
        await monitor.alert_on_issues(metrics)
        await asyncio.sleep(300)  # Check every 5 minutes

if __name__ == "__main__":
    asyncio.run(main())
```

---

## CDN Integration

### 1. Cloudflare Setup

#### DNS Configuration
```bash
# Cloudflare API setup
export CF_API_TOKEN="your-cloudflare-api-token"
export CF_ZONE_ID="your-zone-id"

# Create DNS records via API
curl -X POST "https://api.cloudflare.com/client/v4/zones/${CF_ZONE_ID}/dns_records" \
     -H "Authorization: Bearer ${CF_API_TOKEN}" \
     -H "Content-Type: application/json" \
     --data '{
       "type": "A",
       "name": "custom_domain.app",
       "content": "your-server-ip",
       "ttl": 300,
       "proxied": true
     }'
```

#### Page Rules Configuration
```json
{
  "targets": [
    {
      "target": "url",
      "constraint": {
        "operator": "matches",
        "value": "custom_domain.app/api/*"
      }
    }
  ],
  "actions": [
    {
      "id": "cache_level",
      "value": "bypass"
    },
    {
      "id": "security_level",
      "value": "high"
    },
    {
      "id": "ssl",
      "value": "strict"
    }
  ]
}
```

### 2. Custom CDN Headers

#### Application Headers Configuration
```python
# In main.py - Security headers middleware
async def security_headers_middleware(request, handler):
    response = await handler(request)
    
    # Security headers
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    response.headers['Permissions-Policy'] = 'geolocation=(), microphone=(), camera=()'
    
    # CSP for API endpoints
    if request.path.startswith('/api/'):
        response.headers['Content-Security-Policy'] = "default-src 'none'"
    
    # Rate limit headers
    response.headers['X-RateLimit-Limit'] = '20'
    response.headers['X-RateLimit-Remaining'] = '19'  # Dynamic
    response.headers['X-RateLimit-Reset'] = str(int(time.time()) + 60)
    
    return response
```

---

## Advanced Firewall Configuration

### 1. iptables Advanced Rules

#### Comprehensive Firewall Script
```bash
#!/bin/bash

# Advanced iptables configuration for production

# Clear existing rules
iptables -F
iptables -X
iptables -t nat -F
iptables -t nat -X
iptables -t mangle -F
iptables -t mangle -X

# Set default policies
iptables -P INPUT DROP
iptables -P FORWARD DROP
iptables -P OUTPUT ACCEPT

# Allow loopback
iptables -A INPUT -i lo -j ACCEPT
iptables -A OUTPUT -o lo -j ACCEPT

# Allow established and related connections
iptables -A INPUT -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT

# Create custom chains
iptables -N SSH_PROTECT
iptables -N WEB_PROTECT
iptables -N DDOS_PROTECT
iptables -N LOG_AND_DROP

# SSH protection
iptables -A SSH_PROTECT -p tcp --dport 2222 -m conntrack --ctstate NEW -m recent --set --name ssh_attack
iptables -A SSH_PROTECT -p tcp --dport 2222 -m conntrack --ctstate NEW -m recent --update --seconds 60 --hitcount 4 --name ssh_attack -j LOG_AND_DROP
iptables -A SSH_PROTECT -p tcp --dport 2222 -j ACCEPT

# Web protection  
iptables -A WEB_PROTECT -p tcp --dport 8080 -m conntrack --ctstate NEW -m recent --set --name web_attack
iptables -A WEB_PROTECT -p tcp --dport 8080 -m conntrack --ctstate NEW -m recent --update --seconds 10 --hitcount 20 --name web_attack -j LOG_AND_DROP
iptables -A WEB_PROTECT -p tcp --dport 8080 -m connlimit --connlimit-above 50 -j LOG_AND_DROP
iptables -A WEB_PROTECT -p tcp --dport 8080 -j ACCEPT

iptables -A WEB_PROTECT -p tcp --dport 443 -m conntrack --ctstate NEW -m recent --set --name ssl_attack
iptables -A WEB_PROTECT -p tcp --dport 443 -m conntrack --ctstate NEW -m recent --update --seconds 10 --hitcount 20 --name ssl_attack -j LOG_AND_DROP
iptables -A WEB_PROTECT -p tcp --dport 443 -m connlimit --connlimit-above 50 -j LOG_AND_DROP
iptables -A WEB_PROTECT -p tcp --dport 443 -j ACCEPT

# DDoS protection
iptables -A DDOS_PROTECT -p tcp --syn -m limit --limit 2/s --limit-burst 6 -j RETURN
iptables -A DDOS_PROTECT -p tcp --syn -j LOG_AND_DROP
iptables -A DDOS_PROTECT -p icmp --icmp-type echo-request -m limit --limit 1/s -j ACCEPT
iptables -A DDOS_PROTECT -p icmp --icmp-type echo-request -j LOG_AND_DROP

# Log and drop
iptables -A LOG_AND_DROP -m limit --limit 5/min -j LOG --log-prefix "IPTables-Dropped: "
iptables -A LOG_AND_DROP -j DROP

# Apply protections
iptables -A INPUT -j DDOS_PROTECT
iptables -A INPUT -p tcp --dport 2222 -j SSH_PROTECT
iptables -A INPUT -p tcp -m multiport --dports 8080,443 -j WEB_PROTECT

# Allow ping with rate limiting
iptables -A INPUT -p icmp --icmp-type echo-request -m limit --limit 1/s -j ACCEPT

# Drop everything else
iptables -A INPUT -j LOG_AND_DROP

# Save rules
iptables-save > /etc/iptables/rules.v4
```

### 2. Fail2ban Advanced Configuration

#### Custom Fail2ban Jail
```ini
# /etc/fail2ban/jail.local

[DEFAULT]
bantime = 3600
findtime = 600
maxretry = 3
backend = systemd
destemail = admin@custom_domain.app
sender = fail2ban@custom_domain.app
action = %(action_mwl)s

[sshd]
enabled = true
port = 2222
logpath = %(sshd_log)s
bantime = 86400

[senditbot-api]
enabled = true
port = 8080,443
filter = senditbot-api
logpath = /home/senditbot/logs/bot.log
maxretry = 10
findtime = 300
bantime = 1800

[senditbot-ddos]
enabled = true
port = 8080,443
filter = senditbot-ddos
logpath = /var/log/syslog
maxretry = 100
findtime = 60
bantime = 3600
```

#### Custom Fail2ban Filters
```ini
# /etc/fail2ban/filter.d/senditbot-api.conf
[Definition]
failregex = ^.*Rate limit exceeded.*from <HOST>
            ^.*Invalid request.*from <HOST>
            ^.*Authentication failed.*from <HOST>
            ^.*Suspicious activity.*from <HOST>
ignoreregex =
```

```ini
# /etc/fail2ban/filter.d/senditbot-ddos.conf
[Definition]
failregex = ^.*IPTables-Dropped.*SRC=<HOST>
ignoreregex =
```

---

## Intrusion Detection

### 1. AIDE (Advanced Intrusion Detection Environment)

#### AIDE Setup
```bash
# Install AIDE
sudo apt install -y aide

# Initialize database
sudo aideinit

# Move database
sudo mv /var/lib/aide/aide.db.new /var/lib/aide/aide.db

# Configure monitoring
sudo vim /etc/aide/aide.conf
```

AIDE configuration:
```conf
# Monitor critical files
/home/senditbot/sendit-bot/main.py f+p+u+g+s+m+c+md5+sha1
/home/senditbot/sendit-bot/config/ f+p+u+g+s+m+c+md5+sha1
/home/senditbot/sendit-bot/.env f+p+u+g+s+m+c+md5+sha1
/etc/systemd/system/senditbot.service f+p+u+g+s+m+c+md5+sha1

# Exclude log files
!/home/senditbot/logs/
!/home/senditbot/backups/
```

Daily AIDE check:
```bash
#!/bin/bash
# /home/senditbot/scripts/aide-check.sh

AIDE_OUTPUT=$(aide --check)
AIDE_STATUS=$?

if [ $AIDE_STATUS -ne 0 ]; then
    echo "AIDE detected changes:" | mail -s "AIDE Alert - custom_domain.app" admin@custom_domain.app
    echo "$AIDE_OUTPUT" | mail -s "AIDE Details" admin@custom_domain.app
    
    # Send Discord notification
    curl -X POST "your-discord-webhook-url" \
         -H "Content-Type: application/json" \
         -d '{"content":"🚨 AIDE detected file system changes on custom_domain.app"}'
fi

# Update database weekly
if [ "$(date +%u)" -eq 7 ]; then
    aide --update
    mv /var/lib/aide/aide.db.new /var/lib/aide/aide.db
fi
```

### 2. Log Analysis for Intrusion Detection

#### Security Log Monitor
```python
#!/usr/bin/env python3
import re
import time
from collections import defaultdict, deque
from datetime import datetime, timedelta
import json

class SecurityMonitor:
    def __init__(self):
        self.suspicious_patterns = [
            r'SELECT.*FROM.*information_schema',  # SQL injection
            r'UNION.*SELECT',                     # SQL injection
            r'<script.*>.*</script>',             # XSS
            r'javascript:',                       # XSS
            r'eval\s*\(',                        # Code injection
            r'exec\s*\(',                        # Code injection
            r'/etc/passwd',                       # File inclusion
            r'\.\./',                            # Directory traversal
            r'cmd=',                             # Command injection
        ]
        
        self.failed_attempts = defaultdict(deque)
        self.alert_threshold = 10
        self.time_window = 300  # 5 minutes
        
    def analyze_log_line(self, line):
        alerts = []
        
        # Extract IP and timestamp
        ip_match = re.search(r'(\d+\.\d+\.\d+\.\d+)', line)
        if not ip_match:
            return alerts
        
        ip = ip_match.group(1)
        
        # Check for suspicious patterns
        for pattern in self.suspicious_patterns:
            if re.search(pattern, line, re.IGNORECASE):
                alerts.append({
                    'type': 'suspicious_pattern',
                    'ip': ip,
                    'pattern': pattern,
                    'line': line.strip(),
                    'timestamp': datetime.now().isoformat()
                })
        
        # Track failed attempts
        if 'failed' in line.lower() or 'error' in line.lower():
            now = time.time()
            self.failed_attempts[ip].append(now)
            
            # Clean old attempts
            while (self.failed_attempts[ip] and 
                   self.failed_attempts[ip][0] < now - self.time_window):
                self.failed_attempts[ip].popleft()
            
            # Check threshold
            if len(self.failed_attempts[ip]) >= self.alert_threshold:
                alerts.append({
                    'type': 'repeated_failures',
                    'ip': ip,
                    'count': len(self.failed_attempts[ip]),
                    'timestamp': datetime.now().isoformat()
                })
        
        return alerts
    
    def send_alert(self, alert):
        # Log alert
        with open('/home/senditbot/logs/security-alerts.log', 'a') as f:
            f.write(json.dumps(alert) + '\n')
        
        # Send Discord notification for critical alerts
        if alert['type'] == 'repeated_failures':
            webhook_url = "your-discord-webhook-url"
            message = f"🚨 Security Alert: {alert['count']} failed attempts from {alert['ip']}"
            
            # Send webhook (implement as needed)
            print(f"ALERT: {message}")

# Usage
monitor = SecurityMonitor()

# Monitor log file
import subprocess
proc = subprocess.Popen(['tail', '-F', '/home/senditbot/logs/bot.log'], 
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

for line in proc.stdout:
    alerts = monitor.analyze_log_line(line)
    for alert in alerts:
        monitor.send_alert(alert)
```

---

## Network Performance Optimization

### 1. TCP Tuning

#### Kernel Parameters Optimization
```bash
# /etc/sysctl.conf
# TCP performance tuning for high-traffic server

# Increase system file descriptor limit
fs.file-max = 100000

# TCP settings
net.core.somaxconn = 65535
net.core.netdev_max_backlog = 5000
net.ipv4.tcp_max_syn_backlog = 65535
net.ipv4.tcp_fin_timeout = 10
net.ipv4.tcp_keepalive_time = 1200
net.ipv4.tcp_keepalive_intvl = 15
net.ipv4.tcp_keepalive_probes = 5

# TCP window scaling
net.ipv4.tcp_window_scaling = 1
net.core.rmem_max = 134217728
net.core.wmem_max = 134217728
net.ipv4.tcp_rmem = 4096 87380 134217728
net.ipv4.tcp_wmem = 4096 65536 134217728

# TCP congestion control
net.ipv4.tcp_congestion_control = bbr

# Connection tracking
net.netfilter.nf_conntrack_max = 1000000
net.netfilter.nf_conntrack_tcp_timeout_established = 1800

# Apply settings
sysctl -p
```

### 2. Application-Level Optimization

#### Connection Pooling Configuration
```python
# Enhanced connection handling in main.py
import aiohttp
from aiohttp import web, ClientTimeout, TCPConnector

class OptimizedSenditBot(commands.Bot):
    def __init__(self):
        super().__init__()
        
        # Configure connector with connection pooling
        self.connector = TCPConnector(
            limit=100,              # Total connection pool size
            limit_per_host=10,      # Per-host connection limit
            ttl_dns_cache=300,      # DNS cache TTL
            use_dns_cache=True,     # Enable DNS caching
            keepalive_timeout=300,  # Keep-alive timeout
            enable_cleanup_closed=True
        )
        
        # Configure timeout
        self.timeout = ClientTimeout(
            total=30,               # Total timeout
            connect=10,             # Connection timeout
            sock_read=20            # Socket read timeout
        )
    
    async def setup_web_server(self):
        # Configure web server with performance optimizations
        self.web_app = web.Application(
            client_max_size=1024*1024,  # 1MB max request size
            middlewares=[
                self.compression_middleware,
                self.caching_middleware,
                self.rate_limit_middleware
            ]
        )
        
        # Enable gzip compression
        @web.middleware
        async def compression_middleware(self, request, handler):
            response = await handler(request)
            
            # Compress JSON responses
            if (response.headers.get('Content-Type', '').startswith('application/json') 
                and 'gzip' in request.headers.get('Accept-Encoding', '')):
                response.enable_compression()
            
            return response
        
        # Response caching
        @web.middleware  
        async def caching_middleware(self, request, handler):
            # Cache health checks for 30 seconds
            if request.path == '/api/health':
                response = await handler(request)
                response.headers['Cache-Control'] = 'public, max-age=30'
                return response
            
            return await handler(request)
```

---

## Incident Response

### 1. Incident Detection and Alerting

#### Automated Incident Response Script
```bash
#!/bin/bash

# Incident response automation
INCIDENT_LOG="/home/senditbot/logs/incidents.log"
WEBHOOK_URL="your-discord-webhook-url"

detect_incident() {
    local incident_type=$1
    local details=$2
    local severity=$3
    
    timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    
    # Log incident
    echo "$timestamp [$severity] $incident_type: $details" >> "$INCIDENT_LOG"
    
    # Auto-response based on severity
    case $severity in
        "CRITICAL")
            handle_critical_incident "$incident_type" "$details"
            ;;
        "HIGH")
            handle_high_incident "$incident_type" "$details"
            ;;
        "MEDIUM")
            handle_medium_incident "$incident_type" "$details"
            ;;
    esac
}

handle_critical_incident() {
    local incident_type=$1
    local details=$2
    
    # Immediate actions
    case $incident_type in
        "SERVICE_DOWN")
            systemctl restart senditbot
            ;;
        "DDOS_ATTACK")
            # Enable emergency DDoS protection
            iptables -I INPUT -p tcp --dport 8080 -m limit --limit 1/s --limit-burst 3 -j ACCEPT
            iptables -I INPUT -p tcp --dport 8080 -j DROP
            ;;
        "HIGH_ERROR_RATE")
            # Switch to maintenance mode
            # systemctl stop senditbot
            # systemctl start senditbot-maintenance
            ;;
    esac
    
    # Send immediate alert
    send_discord_alert "🚨 CRITICAL INCIDENT: $incident_type - $details" "critical"
}

send_discord_alert() {
    local message=$1
    local priority=${2:-"normal"}
    
    # Color coding based on priority
    case $priority in
        "critical") color=16711680 ;;  # Red
        "high") color=16753920 ;;      # Orange  
        "medium") color=16776960 ;;    # Yellow
        *) color=3447003 ;;            # Blue
    esac
    
    curl -X POST "$WEBHOOK_URL" \
         -H "Content-Type: application/json" \
         -d "{
           \"embeds\": [{
             \"title\": \"Security Incident\",
             \"description\": \"$message\",
             \"color\": $color,
             \"timestamp\": \"$(date -u +%Y-%m-%dT%H:%M:%S.000Z)\"
           }]
         }"
}

# Monitoring functions
check_service_health() {
    if ! curl -f -s http://localhost:8080/api/health > /dev/null; then
        detect_incident "SERVICE_DOWN" "Health check failed" "CRITICAL"
        return 1
    fi
    return 0
}

check_error_rate() {
    error_count=$(grep -c "ERROR" /home/senditbot/logs/bot.log | tail -100)
    if [ "$error_count" -gt 10 ]; then
        detect_incident "HIGH_ERROR_RATE" "Error rate: $error_count/100 requests" "HIGH"
    fi
}

check_ddos_indicators() {
    # Check for unusual connection patterns
    active_connections=$(ss -tun state established sport = :8080 | wc -l)
    if [ "$active_connections" -gt 1000 ]; then
        detect_incident "POSSIBLE_DDOS" "Active connections: $active_connections" "HIGH"
    fi
}

# Main monitoring loop
while true; do
    check_service_health
    check_error_rate  
    check_ddos_indicators
    sleep 60
done
```

### 2. Recovery Procedures

#### Automated Recovery Script
```bash
#!/bin/bash

# Recovery procedures
BACKUP_DIR="/home/senditbot/backups"

recover_from_backup() {
    local backup_type=$1
    
    case $backup_type in
        "config")
            latest_config=$(ls -t "$BACKUP_DIR"/config_backup_*.tar.gz | head -1)
            if [ -n "$latest_config" ]; then
                systemctl stop senditbot
                tar -xzf "$latest_config" -C /
                systemctl start senditbot
                echo "Config recovered from $latest_config"
            fi
            ;;
        "database")
            latest_db=$(ls -t "$BACKUP_DIR"/db_backup_*.sql.gz | head -1)
            if [ -n "$latest_db" ]; then
                gunzip -c "$latest_db" | psql "$DATABASE_URL"
                echo "Database recovered from $latest_db"
            fi
            ;;
    esac
}

# Health recovery
recover_service_health() {
    echo "Attempting service recovery..."
    
    # Stop service
    systemctl stop senditbot
    sleep 5
    
    # Kill any remaining processes
    pkill -f "python main.py" || true
    
    # Clear temporary files
    rm -f /tmp/senditbot_*
    
    # Start service
    systemctl start senditbot
    
    # Wait and verify
    sleep 10
    if curl -f -s http://localhost:8080/api/health > /dev/null; then
        echo "Service recovery successful"
        send_discord_alert "✅ Service recovery successful" "normal"
        return 0
    else
        echo "Service recovery failed"
        send_discord_alert "❌ Service recovery failed" "critical"
        return 1
    fi
}

# Network recovery
recover_network_issues() {
    echo "Attempting network recovery..."
    
    # Reset iptables to safe defaults
    iptables -F
    iptables -P INPUT DROP
    iptables -P FORWARD DROP  
    iptables -P OUTPUT ACCEPT
    
    # Allow essential traffic
    iptables -A INPUT -i lo -j ACCEPT
    iptables -A INPUT -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT
    iptables -A INPUT -p tcp --dport 2222 -j ACCEPT  # SSH
    iptables -A INPUT -p tcp --dport 8080 -j ACCEPT  # Bot
    iptables -A INPUT -p tcp --dport 443 -j ACCEPT   # HTTPS
    
    # Restart networking
    systemctl restart networking
    
    echo "Network recovery completed"
}
```

This comprehensive network and security guide provides enterprise-level protection and monitoring for your VPS deployment. Implement these configurations gradually and test each component thoroughly before deploying to production.
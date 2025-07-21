# Simple Deployment Guide - No Nginx Required

## Quick Start

The sendit Discord bot runs its own web server directly - **no Nginx needed!**

## 1. VPS Setup

```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Install Python 3.10+
sudo apt install python3 python3-pip python3-venv -y

# Create bot directory
mkdir ~/sendit_bot && cd ~/sendit_bot

# Clone repository
git clone https://github.com/spidey000/sendit_discord_wallet_verif.git .
```

## 2. Environment Setup

```bash
# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Create .env file
nano .env
```

Add to `.env`:
```env
DISCORD_TOKEN=your_discord_bot_token_here
DATABASE_URL=postgresql://postgres.[project_id]:[password]@aws-0-us-east-2.pooler.supabase.com:6543/postgres
JWT_SECRET=your_super_secure_random_32_character_string_here
PORT=8080
```

## 3. Configuration

Edit `config/config.json` to match your Discord server IDs:
```json
{
  "bot_settings": {
    "guild_id": YOUR_GUILD_ID
  },
  "server": {
    "port": 8080,
    "host": "0.0.0.0",
    "ssl": {
      "enabled": false
    }
  }
}
```

## 4. Firewall Setup

```bash
# Allow bot port
sudo ufw allow 8080

# Enable firewall
sudo ufw enable
```

## 5. Run the Bot

### Development Mode
```bash
python main.py
```

### Production Mode (with systemd)
Create service file:
```bash
sudo nano /etc/systemd/system/sendit-bot.service
```

Add:
```ini
[Unit]
Description=Sendit Discord Bot
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/sendit_bot
Environment=PATH=/home/ubuntu/sendit_bot/venv/bin
ExecStart=/home/ubuntu/sendit_bot/venv/bin/python main.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Enable and start:
```bash
sudo systemctl daemon-reload
sudo systemctl enable sendit-bot
sudo systemctl start sendit-bot
sudo systemctl status sendit-bot
```

## 6. SSL Setup (Optional)

### Using Let's Encrypt
```bash
# Install certbot
sudo apt install certbot -y

# Get certificate (bot must be stopped first)
sudo systemctl stop sendit-bot
sudo certbot certonly --standalone -d your-domain.com

# Update .env with SSL paths
echo "SSL_CERT_PATH=/etc/letsencrypt/live/your-domain.com/fullchain.pem" >> .env
echo "SSL_KEY_PATH=/etc/letsencrypt/live/your-domain.com/privkey.pem" >> .env

# Update config.json
# Set "ssl.enabled": true in config/config.json

# Restart bot
sudo systemctl start sendit-bot
```

### Auto-renewal
```bash
# Add cron job for certificate renewal
sudo crontab -e

# Add this line:
0 3 * * * certbot renew --quiet && systemctl restart sendit-bot
```

## 7. Alternative: Using Caddy (If you prefer a reverse proxy)

Install Caddy:
```bash
sudo apt install -y debian-keyring debian-archive-keyring apt-transport-https
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | sudo gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
echo "deb [signed-by=/usr/share/keyrings/caddy-stable-archive-keyring.gpg] https://dl.cloudsmith.io/public/caddy/stable/deb/debian any-version main" | sudo tee /etc/apt/sources.list.d/caddy-stable.list
sudo apt update
sudo apt install caddy
```

Create Caddyfile:
```bash
sudo nano /etc/caddy/Caddyfile
```

Add:
```caddy
your-domain.com {
    reverse_proxy localhost:8080
}
```

Start Caddy:
```bash
sudo systemctl enable caddy
sudo systemctl start caddy
```

## 8. Monitoring

### Check bot status
```bash
sudo systemctl status sendit-bot
```

### View logs
```bash
sudo journalctl -u sendit-bot -f
```

### Test API endpoints
```bash
# Health check
curl http://localhost:8080/api/health

# Or with domain
curl https://your-domain.com/api/health
```

## 9. Frontend Configuration

Update your Vercel frontend to point to your VPS:
- Development: `http://your-vps-ip:8080`
- Production: `https://your-domain.com`

## Troubleshooting

### Port already in use
```bash
# Find what's using the port
sudo lsof -i :8080

# Kill process if needed
sudo kill -9 PID
```

### Permission denied for SSL certificates
```bash
# Add user to ssl-cert group
sudo usermod -a -G ssl-cert ubuntu

# Or use different port (like 8080) and proxy with Caddy
```

### Bot not responding
```bash
# Check logs
sudo journalctl -u sendit-bot -n 50

# Restart bot
sudo systemctl restart sendit-bot
```

## Benefits of This Approach

✅ **Simple**: No Nginx configuration needed
✅ **Direct**: Bot handles HTTP/HTTPS directly  
✅ **Flexible**: Easy to switch to Caddy later
✅ **Secure**: Built-in SSL support with Let's Encrypt
✅ **Reliable**: systemd service management
✅ **Scalable**: Can add load balancer if needed later

The bot is now running directly on your VPS without any reverse proxy complications!
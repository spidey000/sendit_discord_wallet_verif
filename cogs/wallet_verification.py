import discord
from discord.ext import commands
from discord import app_commands
import logging
import asyncio
import jwt
import json
import uuid
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
import aiohttp
from aiohttp import web
import base58
from collections import defaultdict
import os

from shared.database import db
from shared.utils import create_embed, get_message, is_valid_solana_address

logger = logging.getLogger('sendit.wallet_verification')

class WalletVerification(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.jwt_secret = os.getenv('JWT_SECRET') or 'your-jwt-secret-key'
        self.verification_base_url = os.getenv('VERIFICATION_URL', 'https://verify.sendit-bot.com')
        self.rate_limits = defaultdict(list)  # IP-based rate limiting
        self.app = None
        self.server = None
        self.verification_role_name = bot.config.get('roles', {}).get('verified_role_name', 'Verified')
        
    async def cog_load(self):
        """Initialize the cog and start the web server"""
        logger.info("Wallet Verification cog loaded")
        await self.start_api_server()
        
    async def cog_unload(self):
        """Clean up when cog is unloaded"""
        if self.server:
            self.server.close()
            await self.server.wait_closed()
        logger.info("Wallet Verification cog unloaded")
    
    async def start_api_server(self):
        """Start the aiohttp API server for verification endpoints"""
        # Only start server if verification URL is configured for local hosting
        if not self.verification_base_url.startswith('http://localhost') and not self.verification_base_url.startswith('http://127.0.0.1'):
            logger.info("External verification URL configured, skipping local API server")
            return
            
        try:
            self.app = web.Application()
            
            # Add CORS middleware
            async def cors_middleware(request, handler):
                response = await handler(request)
                response.headers['Access-Control-Allow-Origin'] = '*'
                response.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
                response.headers['Access-Control-Allow-Headers'] = 'Content-Type'
                return response
            
            self.app.middlewares.append(cors_middleware)
            
            # Setup routes
            self.app.router.add_get('/verify/{token}', self.handle_verification_page)
            self.app.router.add_post('/api/verify', self.handle_verification_submit)
            self.app.router.add_options('/api/verify', self.handle_options)
            self.app.router.add_get('/health', self.handle_health)
            
            # Start server
            port = int(os.getenv('API_PORT', '8080'))
            runner = web.AppRunner(self.app)
            await runner.setup()
            site = web.TCPSite(runner, '0.0.0.0', port)
            await site.start()
            logger.info(f"API server started on port {port}")
            
        except Exception as e:
            logger.error(f"Failed to start API server: {e}")
    
    async def handle_options(self, request):
        """Handle CORS preflight requests"""
        return web.Response(
            headers={
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
                'Access-Control-Allow-Headers': 'Content-Type'
            }
        )
    
    async def handle_health(self, request):
        """Health check endpoint"""
        return web.json_response({'status': 'healthy', 'timestamp': datetime.utcnow().isoformat()})
    
    async def handle_verification_page(self, request):
        """Serve the verification page"""
        token = request.match_info['token']
        
        # Validate token
        token_data = await self.get_verification_token(token)
        if not token_data:
            return web.Response(
                text=self.get_error_page("Invalid or expired verification token"),
                content_type='text/html'
            )
        
        # Generate the verification page HTML
        html = self.generate_verification_page(token, token_data)
        return web.Response(text=html, content_type='text/html')
    
    async def handle_verification_submit(self, request):
        """Handle wallet verification submission"""
        client_ip = request.remote
        
        # Rate limiting check
        if not await self.check_rate_limit(client_ip):
            return web.json_response(
                {'success': False, 'error': 'Rate limit exceeded. Please try again later.'},
                status=429
            )
        
        try:
            data = await request.json()
            
            token = data.get('token')
            wallet_address = data.get('walletAddress')
            signature = data.get('signature')
            
            if not all([token, wallet_address, signature]):
                return web.json_response(
                    {'success': False, 'error': get_message('solana_wallet_verification.missing_data')},
                    status=400
                )
            
            # Validate wallet address format
            if not is_valid_solana_address(wallet_address):
                return web.json_response(
                    {'success': False, 'error': get_message('solana_wallet_verification.invalid_wallet')},
                    status=400
                )
            
            # Get and validate token
            token_data = await self.get_verification_token(token)
            if not token_data:
                return web.json_response(
                    {'success': False, 'error': get_message('solana_wallet_verification.invalid_token')},
                    status=400
                )
            
            # Verify signature
            verification_result = await self.verify_wallet_signature(
                wallet_address, signature, token_data['token']
            )
            
            if not verification_result['valid']:
                return web.json_response(
                    {'success': False, 'error': verification_result['error']},
                    status=400
                )
            
            # Complete verification
            success = await self.complete_verification(
                token_data, wallet_address, client_ip
            )
            
            if success:
                return web.json_response({
                    'success': True,
                    'message': get_message('solana_wallet_verification.verification_success_frontend')
                })
            else:
                return web.json_response(
                    {'success': False, 'error': get_message('solana_wallet_verification.internal_server_error')},
                    status=500
                )
                
        except Exception as e:
            logger.error(f"Error in verification submission: {e}")
            return web.json_response(
                {'success': False, 'error': get_message('solana_wallet_verification.internal_server_error')},
                status=500
            )
    
    async def check_rate_limit(self, ip: str) -> bool:
        """Check if IP is within rate limits (10 requests per minute)"""
        now = datetime.utcnow()
        minute_ago = now - timedelta(minutes=1)
        
        # Clean old entries
        self.rate_limits[ip] = [
            timestamp for timestamp in self.rate_limits[ip] 
            if timestamp > minute_ago
        ]
        
        # Check limit
        if len(self.rate_limits[ip]) >= 10:
            return False
        
        # Add current request
        self.rate_limits[ip].append(now)
        return True
    
    def generate_verification_page(self, token: str, token_data: Dict) -> str:
        """Generate the HTML verification page"""
        return f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Solana Wallet Verification - sendit</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ 
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh; display: flex; align-items: center; justify-content: center;
        }}
        .container {{ 
            background: white; border-radius: 16px; padding: 2rem; max-width: 500px; width: 90%;
            box-shadow: 0 20px 40px rgba(0,0,0,0.1); text-align: center;
        }}
        .logo {{ color: #667eea; font-size: 2rem; font-weight: bold; margin-bottom: 1rem; }}
        h1 {{ color: #333; margin-bottom: 0.5rem; }}
        .description {{ color: #666; margin-bottom: 2rem; line-height: 1.6; }}
        .verification-info {{ 
            background: #f8f9fa; border-radius: 8px; padding: 1rem; margin-bottom: 2rem;
            border-left: 4px solid #667eea;
        }}
        .message-to-sign {{ 
            font-family: 'Courier New', monospace; background: #2d3748; color: #e2e8f0;
            padding: 1rem; border-radius: 8px; margin: 1rem 0; word-break: break-all;
        }}
        .btn {{ 
            background: #667eea; color: white; border: none; padding: 12px 24px;
            border-radius: 8px; font-size: 1rem; cursor: pointer; transition: all 0.2s;
            margin: 0.5rem; min-width: 120px;
        }}
        .btn:hover {{ background: #5a6fd8; transform: translateY(-1px); }}
        .btn:disabled {{ background: #ccc; cursor: not-allowed; transform: none; }}
        .status {{ margin-top: 1rem; padding: 1rem; border-radius: 8px; }}
        .status.success {{ background: #d4edda; color: #155724; border: 1px solid #c3e6cb; }}
        .status.error {{ background: #f8d7da; color: #721c24; border: 1px solid #f5c6cb; }}
        .status.info {{ background: #d1ecf1; color: #0c5460; border: 1px solid #bee5eb; }}
        .spinner {{ display: none; width: 20px; height: 20px; border: 2px solid #f3f3f3;
            border-top: 2px solid #667eea; border-radius: 50%; animation: spin 1s linear infinite;
            margin: 0 auto;
        }}
        @keyframes spin {{ 0% {{ transform: rotate(0deg); }} 100% {{ transform: rotate(360deg); }} }}
    </style>
</head>
<body>
    <div class="container">
        <div class="logo">🔐 sendit</div>
        <h1>Verify Your Solana Wallet</h1>
        <p class="description">
            Connect your Solana wallet and sign a message to verify ownership and unlock XP earning in the Discord server.
        </p>
        
        <div class="verification-info">
            <strong>Message to sign:</strong>
            <div class="message-to-sign">Confirming wallet ownership for request: {token_data.get('token', 'unknown')}</div>
        </div>
        
        <button id="connectBtn" class="btn" onclick="connectWallet()">Connect Wallet</button>
        <button id="signBtn" class="btn" onclick="signMessage()" style="display: none;" disabled>Sign Message</button>
        
        <div class="spinner" id="spinner"></div>
        <div id="status"></div>
    </div>

    <script>
        let walletAddress = null;
        let provider = null;
        const messageToSign = "Confirming wallet ownership for request: {token_data.get('token', 'unknown')}";
        
        async function connectWallet() {{
            try {{
                if (window.solana && window.solana.isPhantom) {{
                    provider = window.solana;
                }} else if (window.solflare && window.solflare.isSolflare) {{
                    provider = window.solflare;
                }} else {{
                    showStatus('error', 'Please install Phantom or Solflare wallet extension');
                    return;
                }}
                
                showSpinner(true);
                showStatus('info', 'Connecting to wallet...');
                
                const response = await provider.connect();
                walletAddress = response.publicKey.toString();
                
                showStatus('success', `Connected: ${{walletAddress.substring(0, 8)}}...${{walletAddress.substring(-8)}}`);
                
                document.getElementById('connectBtn').style.display = 'none';
                document.getElementById('signBtn').style.display = 'inline-block';
                document.getElementById('signBtn').disabled = false;
                
            }} catch (error) {{
                console.error('Wallet connection error:', error);
                showStatus('error', 'Failed to connect wallet: ' + error.message);
            }} finally {{
                showSpinner(false);
            }}
        }}
        
        async function signMessage() {{
            if (!walletAddress || !provider) {{
                showStatus('error', 'Please connect your wallet first');
                return;
            }}
            
            try {{
                showSpinner(true);
                showStatus('info', 'Please sign the message in your wallet...');
                
                const encodedMessage = new TextEncoder().encode(messageToSign);
                const signedMessage = await provider.signMessage(encodedMessage, 'utf8');
                
                showStatus('info', 'Submitting verification...');
                
                const response = await fetch('/api/verify', {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: JSON.stringify({{
                        token: '{token}',
                        walletAddress: walletAddress,
                        signature: Array.from(signedMessage.signature)
                    }})
                }});
                
                const result = await response.json();
                
                if (result.success) {{
                    showStatus('success', result.message + ' You can now close this page and return to Discord.');
                    document.getElementById('signBtn').disabled = true;
                }} else {{
                    showStatus('error', result.error || 'Verification failed');
                }}
                
            }} catch (error) {{
                console.error('Signing error:', error);
                showStatus('error', 'Failed to sign message: ' + error.message);
            }} finally {{
                showSpinner(false);
            }}
        }}
        
        function showStatus(type, message) {{
            const statusDiv = document.getElementById('status');
            statusDiv.className = `status ${{type}}`;
            statusDiv.textContent = message;
            statusDiv.style.display = 'block';
        }}
        
        function showSpinner(show) {{
            document.getElementById('spinner').style.display = show ? 'block' : 'none';
        }}
        
        // Auto-connect if wallet is already connected
        window.addEventListener('load', async () => {{
            if (window.solana && window.solana.isConnected) {{
                provider = window.solana;
                walletAddress = window.solana.publicKey.toString();
                showStatus('success', `Already connected: ${{walletAddress.substring(0, 8)}}...${{walletAddress.substring(-8)}}`);
                document.getElementById('connectBtn').style.display = 'none';
                document.getElementById('signBtn').style.display = 'inline-block';
                document.getElementById('signBtn').disabled = false;
            }}
        }});
    </script>
</body>
</html>
        """
    
    def get_error_page(self, error_message: str) -> str:
        """Generate error page HTML"""
        return f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Verification Error - sendit</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ 
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh; display: flex; align-items: center; justify-content: center;
        }}
        .container {{ 
            background: white; border-radius: 16px; padding: 2rem; max-width: 500px; width: 90%;
            box-shadow: 0 20px 40px rgba(0,0,0,0.1); text-align: center;
        }}
        .logo {{ color: #667eea; font-size: 2rem; font-weight: bold; margin-bottom: 1rem; }}
        .error {{ color: #721c24; background: #f8d7da; padding: 1rem; border-radius: 8px; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="logo">🔐 sendit</div>
        <h1>Verification Error</h1>
        <div class="error">{error_message}</div>
        <p style="margin-top: 1rem; color: #666;">
            Please request a new verification link from the Discord server.
        </p>
    </div>
</body>
</html>
        """
    
    async def generate_jwt_token(self, discord_id: str, discord_user_id: str) -> str:
        """Generate JWT token with 10-minute expiration"""
        payload = {
            'discord_id': discord_id,
            'discord_user_id': discord_user_id,
            'exp': datetime.utcnow() + timedelta(minutes=10),
            'iat': datetime.utcnow(),
            'token_uuid': str(uuid.uuid4())
        }
        
        return jwt.encode(payload, self.jwt_secret, algorithm='HS256')
    
    async def verify_jwt_token(self, token: str) -> Optional[Dict]:
        """Verify and decode JWT token"""
        try:
            payload = jwt.decode(token, self.jwt_secret, algorithms=['HS256'])
            return payload
        except jwt.ExpiredSignatureError:
            return None
        except jwt.InvalidTokenError:
            return None
    
    async def store_verification_token(self, token: str, discord_id: str, discord_user_id: str) -> bool:
        """Store verification token in database"""
        expires_at = (datetime.utcnow() + timedelta(minutes=10)).isoformat()
        metadata = {'created_via': 'discord_command'}
        return await db.create_verification_token(token, discord_id, discord_user_id, expires_at, metadata)
    
    async def get_verification_token(self, token: str) -> Optional[Dict]:
        """Get verification token from database"""
        return await db.get_verification_token(token)
    
    async def verify_wallet_signature(self, wallet_address: str, signature: list, token: str) -> Dict[str, Any]:
        """Verify Solana wallet signature using basic validation"""
        try:
            # Basic validation - in production, you'd use proper Solana signature verification
            # For now, we'll do basic checks and assume wallet connection implies ownership
            
            # Validate signature format
            if not isinstance(signature, list) or len(signature) != 64:
                return {
                    'valid': False, 
                    'error': get_message('solana_wallet_verification.signature_invalid')
                }
            
            # Validate wallet address format
            if not is_valid_solana_address(wallet_address):
                return {
                    'valid': False, 
                    'error': get_message('solana_wallet_verification.invalid_wallet')
                }
            
            # For now, we'll accept any properly formatted signature
            # In production, implement full ed25519 signature verification
            logger.info(f"Signature validation passed for wallet {wallet_address}")
            return {'valid': True, 'error': None}
            
        except Exception as e:
            logger.error(f"Signature verification failed: {e}")
            return {
                'valid': False, 
                'error': get_message('solana_wallet_verification.signature_invalid')
            }
    
    async def complete_verification(self, token_data: Dict, wallet_address: str, ip_address: str) -> bool:
        """Complete the verification process"""
        try:
            discord_id = token_data['discord_id']
            discord_user_id = token_data['discord_user_id']
            token = token_data['token']
            
            # Check if wallet is already linked to another user
            existing_user = await db.get_user_by_wallet(wallet_address)
            if existing_user and existing_user['discord_id'] != discord_id:
                logger.warning(f"Wallet {wallet_address} already linked to user {existing_user['discord_id']}")
                return False
            
            # Update verification token status
            await db.complete_verification_token(token, wallet_address, ip_address)
            
            # Link wallet to user
            success = await db.link_wallet(discord_id, wallet_address)
            
            if success:
                # Assign verified role
                await self.assign_verified_role(discord_user_id)
                
                # Send success DM
                await self.send_verification_success_dm(discord_user_id, wallet_address)
                
                # Log analytics
                await db.log_analytics_event(
                    'wallet_verification_completed',
                    discord_id,
                    'global',
                    {
                        'wallet_address': wallet_address,
                        'ip_address': ip_address,
                        'verification_method': 'signature'
                    }
                )
                
                logger.info(f"Wallet verification completed for user {discord_id} with wallet {wallet_address}")
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"Failed to complete verification: {e}")
            return False
    
    async def assign_verified_role(self, discord_user_id: str):
        """Assign verified role to user"""
        try:
            user = self.bot.get_user(int(discord_user_id))
            if not user:
                return
            
            # Find the user in all guilds and assign role
            for guild in self.bot.guilds:
                member = guild.get_member(int(discord_user_id))
                if member:
                    role = discord.utils.get(guild.roles, name=self.verification_role_name)
                    if role and role not in member.roles:
                        await member.add_roles(role)
                        logger.info(f"Assigned {self.verification_role_name} role to {member.display_name} in {guild.name}")
                        
        except Exception as e:
            logger.error(f"Failed to assign verified role: {e}")
    
    async def send_verification_success_dm(self, discord_user_id: str, wallet_address: str):
        """Send verification success DM to user"""
        try:
            user = self.bot.get_user(int(discord_user_id))
            if user:
                embed = create_embed(
                    title="🎉 Wallet Verification Successful!",
                    description=get_message(
                        'solana_wallet_verification.verification_success_dm',
                        wallet=wallet_address
                    ),
                    color=discord.Color.green()
                )
                
                await user.send(embed=embed)
                
        except Exception as e:
            logger.error(f"Failed to send verification success DM: {e}")
    
    # Discord Commands
    
    @commands.hybrid_command(name="solana-verify", help="Verify your Solana wallet to start earning XP")
    async def verify_wallet(self, ctx):
        """Start wallet verification process"""
        # Handle both slash and text commands
        if hasattr(ctx, 'interaction') and ctx.interaction:
            user = ctx.interaction.user
            respond = ctx.interaction.response.send_message
        else:
            user = ctx.author
            respond = ctx.send
        
        user_id = str(user.id)
        
        try:
            # Check if user is already verified
            user_data = await db.get_user(user_id)
            if user_data and user_data.get('wallet_verified'):
                wallet = user_data.get('wallet_address', 'Unknown')
                await respond(
                    get_message('solana_wallet_verification.already_verified', wallet=wallet),
                    ephemeral=True
                )
                return
            
            # Check for pending verification
            pending_token = await db.get_pending_verification(user_id)
            
            if pending_token:
                # Decode token to get UUID
                token_payload = await self.verify_jwt_token(pending_token['token'])
                if token_payload:
                    link = f"{self.verification_base_url}/verify/{pending_token['token']}"
                    await respond(
                        get_message(
                            'solana_wallet_verification.verification_pending',
                            link=link,
                            token_uuid=token_payload.get('token_uuid', 'unknown')
                        ),
                        ephemeral=True
                    )
                    return
            
            # Create new verification token
            token = await self.generate_jwt_token(user_id, user_id)
            token_payload = await self.verify_jwt_token(token)
            
            # Store token in database
            stored = await self.store_verification_token(token, user_id, user_id)
            
            if not stored:
                await respond(
                    get_message('solana_wallet_verification.internal_server_error'),
                    ephemeral=True
                )
                return
            
            # Generate verification link
            verification_link = f"{self.verification_base_url}/verify/{token}"
            
            # Try to send DM
            try:
                embed = create_embed(
                    title="🔐 Verify Your Solana Wallet",
                    description=get_message(
                        'solana_wallet_verification.verification_dm',
                        link=verification_link,
                        token_uuid=token_payload.get('token_uuid', 'unknown')
                    ),
                    color=discord.Color.blue()
                )
                
                await user.send(embed=embed)
                
                # Confirm DM sent
                await respond(
                    get_message('solana_wallet_verification.verification_link_sent'),
                    ephemeral=True
                )
                
            except discord.Forbidden:
                # DMs disabled, send ephemeral message with link
                await respond(
                    get_message(
                        'solana_wallet_verification.verification_link_ephemeral',
                        link=verification_link,
                        token_uuid=token_payload.get('token_uuid', 'unknown')
                    ),
                    ephemeral=True
                )
            
            # Log analytics
            await db.log_analytics_event(
                'verification_request_created',
                user_id,
                str(ctx.guild.id) if ctx.guild else 'dm',
                {
                    'token_uuid': token_payload.get('token_uuid'),
                    'delivery_method': 'dm' if ctx.guild else 'ephemeral'
                }
            )
            
        except Exception as e:
            logger.error(f"Error in verify_wallet command: {e}")
            await respond(
                get_message('solana_wallet_verification.generic_error'),
                ephemeral=True
            )
    
    @commands.command(name="setup-verification")
    @commands.has_permissions(administrator=True)
    async def setup_verification_button(self, ctx):
        """Setup persistent verification button (admin only)"""
        try:
            embed = create_embed(
                title=get_message('solana_wallet_verification.verification_persistent_title'),
                description=get_message('solana_wallet_verification.verification_persistent_description'),
                color=discord.Color.blue()
            )
            
            view = VerificationView()
            await ctx.send(embed=embed, view=view)
            await ctx.message.delete()  # Delete the setup command
            
        except Exception as e:
            logger.error(f"Error setting up verification button: {e}")
            await ctx.send("Failed to setup verification button.", ephemeral=True)
    
    @commands.hybrid_command(name="verification-stats", help="View verification statistics")
    @commands.has_permissions(administrator=True)
    async def verification_stats(self, ctx):
        """View verification statistics (admin only)"""
        # Handle both slash and text commands
        if hasattr(ctx, 'interaction') and ctx.interaction:
            respond = ctx.interaction.response.send_message
        else:
            respond = ctx.send
        
        try:
            # Get verification statistics
            stats_query = """
                SELECT 
                    COUNT(*) FILTER (WHERE wallet_verified = true) as verified_users,
                    COUNT(*) FILTER (WHERE wallet_verified = false) as unverified_users,
                    COUNT(DISTINCT wallet_address) FILTER (WHERE wallet_address IS NOT NULL) as unique_wallets
                FROM users
            """
            
            token_stats_query = """
                SELECT 
                    COUNT(*) FILTER (WHERE status = 'pending') as pending_tokens,
                    COUNT(*) FILTER (WHERE status = 'completed') as completed_tokens,
                    COUNT(*) FILTER (WHERE expires_at < NOW()) as expired_tokens
                FROM verification_tokens
                WHERE created_at > NOW() - INTERVAL '24 hours'
            """
            
            stats = await db.fetchone(stats_query)
            token_stats = await db.fetchone(token_stats_query)
            
            embed = create_embed(
                title="📊 Verification Statistics",
                description="Current verification system statistics",
                color=discord.Color.blue(),
                fields=[
                    {"name": "✅ Verified Users", "value": str(stats['verified_users']), "inline": True},
                    {"name": "❌ Unverified Users", "value": str(stats['unverified_users']), "inline": True},
                    {"name": "🔗 Unique Wallets", "value": str(stats['unique_wallets']), "inline": True},
                    {"name": "⏳ Pending Tokens (24h)", "value": str(token_stats['pending_tokens']), "inline": True},
                    {"name": "✅ Completed (24h)", "value": str(token_stats['completed_tokens']), "inline": True},
                    {"name": "⏰ Expired (24h)", "value": str(token_stats['expired_tokens']), "inline": True}
                ]
            )
            
            await respond(embed=embed, ephemeral=True)
            
        except Exception as e:
            logger.error(f"Error in verification_stats command: {e}")
            await respond("Failed to fetch verification statistics.", ephemeral=True)


class VerificationView(discord.ui.View):
    """Persistent view for wallet verification button"""
    
    def __init__(self):
        super().__init__(timeout=None)
    
    @discord.ui.button(
        label="🔐 Verify Wallet",
        style=discord.ButtonStyle.primary,
        custom_id="verify_wallet_button"
    )
    async def verify_wallet_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Handle wallet verification button click"""
        user_id = str(interaction.user.id)
        
        try:
            # Get the wallet verification cog
            cog = interaction.client.get_cog('WalletVerification')
            if not cog:
                await interaction.response.send_message(
                    get_message('solana_wallet_verification.config_error'),
                    ephemeral=True
                )
                return
            
            # Check if user is already verified
            user_data = await db.get_user(user_id)
            if user_data and user_data.get('wallet_verified'):
                wallet = user_data.get('wallet_address', 'Unknown')
                await interaction.response.send_message(
                    get_message('solana_wallet_verification.already_verified', wallet=wallet),
                    ephemeral=True
                )
                return
            
            # Check for pending verification
            pending_token = await db.get_pending_verification(user_id)
            
            if pending_token:
                # Decode token to get UUID
                token_payload = await cog.verify_jwt_token(pending_token['token'])
                if token_payload:
                    link = f"{cog.verification_base_url}/verify/{pending_token['token']}"
                    await interaction.response.send_message(
                        get_message(
                            'solana_wallet_verification.verification_pending',
                            link=link,
                            token_uuid=token_payload.get('token_uuid', 'unknown')
                        ),
                        ephemeral=True
                    )
                    return
            
            # Create new verification token
            token = await cog.generate_jwt_token(user_id, user_id)
            token_payload = await cog.verify_jwt_token(token)
            
            # Store token in database
            stored = await cog.store_verification_token(token, user_id, user_id)
            
            if not stored:
                await interaction.response.send_message(
                    get_message('solana_wallet_verification.internal_server_error'),
                    ephemeral=True
                )
                return
            
            # Generate verification link
            verification_link = f"{cog.verification_base_url}/verify/{token}"
            
            # Try to send DM
            try:
                embed = create_embed(
                    title="🔐 Verify Your Solana Wallet",
                    description=get_message(
                        'solana_wallet_verification.verification_dm',
                        link=verification_link,
                        token_uuid=token_payload.get('token_uuid', 'unknown')
                    ),
                    color=discord.Color.blue()
                )
                
                await interaction.user.send(embed=embed)
                
                # Confirm DM sent
                await interaction.response.send_message(
                    get_message('solana_wallet_verification.verification_link_sent'),
                    ephemeral=True
                )
                
            except discord.Forbidden:
                # DMs disabled, send ephemeral message with link
                await interaction.response.send_message(
                    get_message(
                        'solana_wallet_verification.verification_link_ephemeral',
                        link=verification_link,
                        token_uuid=token_payload.get('token_uuid', 'unknown')
                    ),
                    ephemeral=True
                )
            
            # Log analytics
            await db.log_analytics_event(
                'verification_request_created',
                user_id,
                str(interaction.guild.id) if interaction.guild else 'dm',
                {
                    'token_uuid': token_payload.get('token_uuid'),
                    'delivery_method': 'dm_attempt',
                    'triggered_by': 'button'
                }
            )
            
        except Exception as e:
            logger.error(f"Error in verification button: {e}")
            await interaction.response.send_message(
                get_message('solana_wallet_verification.generic_error'),
                ephemeral=True
            )


async def setup(bot):
    await bot.add_cog(WalletVerification(bot))
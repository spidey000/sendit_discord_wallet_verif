import discord
from discord.ext import commands
import asyncio
import aiohttp
from aiohttp import web, web_middlewares
import ssl
import json
import os
from pathlib import Path
import logging
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load configuration
def load_config():
    config_path = Path('config/config.json')
    if config_path.exists():
        with open(config_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}

class SenditBot(commands.Bot):
    def __init__(self):
        self.config = load_config()
        
        intents = discord.Intents.default()
        intents.message_content = True
        intents.guilds = True
        intents.members = True
        
        super().__init__(
            command_prefix=self.config.get('prefix', '!'),
            intents=intents,
            help_command=None
        )
        
        self.web_app = None
        self.runner = None
        self.site = None

    async def setup_hook(self):
        """Setup web server and load cogs"""
        await self.setup_web_server()
        await self.load_cogs()

    async def setup_web_server(self):
        """Setup aiohttp web server for API endpoints"""
        self.web_app = web.Application()
        
        # Add CORS middleware  
        try:
            import aiohttp_cors
            cors = aiohttp_cors.setup(self.web_app, defaults={
                "*": aiohttp_cors.ResourceOptions(
                    allow_credentials=True,
                    expose_headers="*",
                    allow_headers="*",
                    allow_methods="*"
                )
            })
        except ImportError:
            logger.warning("aiohttp_cors not available - CORS not configured")
            cors = None
        
        # Setup routes
        self.web_app.router.add_post('/api/confirm', self.handle_wallet_verification)
        self.web_app.router.add_get('/api/health', self.handle_health_check)
        
        # Add CORS to all routes
        if cors:
            for route in list(self.web_app.router.routes()):
                cors.add(route)

    async def load_cogs(self):
        """Load bot cogs/extensions"""
        try:
            # Check if cog file exists before loading
            cog_path = Path('cogs/wallet_verification.py')
            if cog_path.exists():
                await self.load_extension('cogs.wallet_verification')
                logger.info("Loaded wallet_verification cog")
            else:
                logger.warning("wallet_verification cog not found - skipping")
        except Exception as e:
            logger.error(f"Failed to load cog: {e}")

    async def handle_wallet_verification(self, request):
        """Handle wallet verification API endpoint"""
        try:
            data = await request.json()
            # Import verification logic from cog
            cog = self.get_cog('WalletVerification')
            if cog:
                result = await cog.verify_wallet_signature(data)
                return web.json_response(result)
            else:
                return web.json_response(
                    {"error": "Verification service unavailable"}, 
                    status=500
                )
        except Exception as e:
            logger.error(f"Verification error: {e}")
            return web.json_response(
                {"error": "Invalid request"}, 
                status=400
            )

    async def handle_health_check(self, request):
        """Health check endpoint"""
        return web.json_response({
            "status": "healthy",
            "bot_ready": self.is_ready(),
            "guilds": len(self.guilds)
        })

    async def start_web_server(self):
        """Start the web server"""
        # Server configuration
        port = int(os.getenv('PORT', 8080))  # Default to 8080 for development
        host = '0.0.0.0'
        
        # SSL configuration (optional - can be added later)
        ssl_context = None
        cert_path = os.getenv('SSL_CERT_PATH')
        key_path = os.getenv('SSL_KEY_PATH')
        
        if cert_path and key_path and Path(cert_path).exists() and Path(key_path).exists():
            ssl_context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
            ssl_context.load_cert_chain(cert_path, key_path)
            logger.info("SSL context loaded - running HTTPS server")
        else:
            logger.info("No SSL certificates found - running HTTP server")
            logger.info("Set SSL_CERT_PATH and SSL_KEY_PATH environment variables for HTTPS")

        # Ensure web_app is initialized
        if self.web_app is None:
            await self.setup_web_server()
            
        # Start web server
        self.runner = web.AppRunner(self.web_app)
        await self.runner.setup()
        
        self.site = web.TCPSite(
            self.runner, 
            host, 
            port, 
            ssl_context=ssl_context
        )
        
        await self.site.start()
        
        protocol = "https" if ssl_context else "http"
        logger.info(f"Web server started on {protocol}://{host}:{port}")
        
        # Log available endpoints
        logger.info("Available API endpoints:")
        for route in self.web_app.router.routes():
            logger.info(f"  {route.method} {protocol}://{host}:{port}{route.resource.canonical}")

    async def close(self):
        """Cleanup on bot shutdown"""
        if self.site:
            await self.site.stop()
        if self.runner:
            await self.runner.cleanup()
        await super().close()

    async def on_ready(self):
        """Bot ready event"""
        logger.info(f'{self.user} has connected to Discord!')
        logger.info(f'Bot is in {len(self.guilds)} guilds')

async def main():
    """Main function to run bot and web server concurrently"""
    
    # Get Discord token
    token = os.getenv('DISCORD_TOKEN')
    if not token:
        logger.error("DISCORD_TOKEN environment variable not set!")
        return

    # Create bot instance
    bot = SenditBot()
    
    try:
        # Start web server
        await bot.start_web_server()
        
        # Start Discord bot
        await bot.start(token)
        
    except KeyboardInterrupt:
        logger.info("Received keyboard interrupt - shutting down...")
    except Exception as e:
        logger.error(f"Error running bot: {e}")
    finally:
        await bot.close()

if __name__ == '__main__':
    # Handle missing dependencies gracefully
    try:
        import aiohttp_cors
    except ImportError:
        logger.error("aiohttp_cors not installed. Run: pip install aiohttp_cors")
        exit(1)
    
    # Run the bot
    asyncio.run(main())
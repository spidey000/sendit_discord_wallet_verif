#!/usr/bin/env python3
"""
Lightweight health check script for Docker container
Replaces curl dependency for container health monitoring
"""

import sys
import asyncio
import aiohttp
import os
from typing import Optional

async def check_health() -> bool:
    """Check if the bot's HTTP server is responding"""
    port = os.getenv('PORT', '8080')
    url = f"http://localhost:{port}/api/health"
    
    try:
        timeout = aiohttp.ClientTimeout(total=5)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url) as response:
                return response.status == 200
    except Exception:
        return False

def main() -> None:
    """Main health check entry point"""
    try:
        is_healthy = asyncio.run(check_health())
        sys.exit(0 if is_healthy else 1)
    except Exception:
        sys.exit(1)

if __name__ == "__main__":
    main()
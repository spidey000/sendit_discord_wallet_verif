import asyncpg
import os
import json
import asyncio
from loguru import logger
import discord
from typing import Optional, Callable, Any


def escape_sql_value(value):
    """Safely escape SQL values for transaction pooler that doesn't support PREPARE statements."""
    if value is None:
        return 'NULL'
    elif isinstance(value, bool):
        return 'TRUE' if value else 'FALSE'
    elif isinstance(value, (int, float)):
        return str(value)
    elif isinstance(value, str):
        # Escape single quotes by doubling them
        escaped = value.replace("'", "''")
        return f"'{escaped}'"
    else:
        # Convert to string and escape
        escaped = str(value).replace("'", "''")
        return f"'{escaped}'"

async def handle_db_error(interaction: Optional[discord.Interaction], error: Exception, operation: str = "database operation") -> bool:
    """
    Handle database errors with user-friendly messages and logging.
    
    Args:
        interaction: Discord interaction to respond to (None for non-interaction contexts)
        error: The exception that occurred
        operation: Description of the operation that failed
    
    Returns:
        bool: True if error was handled and user was notified, False otherwise
    """
    error_message = "⚠️ **Database Connection Issue**\nThe bot is experiencing database connectivity problems. Please try again in a few moments."
    
    # Log the error with context
    logger.error(f"Database error during {operation}: {type(error).__name__}: {error}")
    
    # Check if it's a connection-related error
    if isinstance(error, (asyncpg.PostgresConnectionError, ConnectionError, OSError)):
        # This is definitely a connection issue
        logger.critical(f"Database connection lost during {operation}")
        
        # Log to Discord if available
        try:
            from shared.logging import discord_logger
            if discord_logger:
                user_id = interaction.user.id if interaction else None
                await discord_logger.log_database_error(error, operation, user_id)
        except Exception as log_error:
            logger.error(f"Failed to log database error to Discord: {log_error}")
        
        if interaction:
            try:
                if interaction.response.is_done():
                    await interaction.followup.send(error_message, ephemeral=True)
                else:
                    await interaction.response.send_message(error_message, ephemeral=True)
                return True
            except Exception as e:
                logger.error(f"Failed to send database error message to user: {e}")
                return False
        else:
            # For non-interaction contexts, we still log but can't notify user directly
            return True
    
    # For other database errors, log but don't assume it's a connection issue
    elif isinstance(error, asyncpg.PostgresError):
        logger.error(f"PostgreSQL error during {operation}: {error}")
        
        # Log to Discord if available
        try:
            from shared.logging import discord_logger
            if discord_logger:
                user_id = interaction.user.id if interaction else None
                await discord_logger.log_database_error(error, operation, user_id)
        except Exception as log_error:
            logger.error(f"Failed to log database error to Discord: {log_error}")
        
        if interaction:
            try:
                fallback_message = "❌ **Error**\nSomething went wrong. Please try again later."
                if interaction.response.is_done():
                    await interaction.followup.send(fallback_message, ephemeral=True)
                else:
                    await interaction.response.send_message(fallback_message, ephemeral=True)
                return True
            except Exception as e:
                logger.error(f"Failed to send database error message to user: {e}")
                return False
        else:
            return True
    
    # Not a database error we recognize
    return False

# Placeholder for database connection pool
_pool = None

async def get_db_connection(max_retries: int = 3, retry_delay: float = 2.0):
    """
    Establishes and returns a database connection pool with retry logic.
    
    Args:
        max_retries: Maximum number of connection attempts
        retry_delay: Delay between retry attempts in seconds
    
    Returns:
        asyncpg.Pool: Database connection pool
    
    Raises:
        ConnectionError: If unable to establish connection after all retries
    """
    global _pool
    
    if _pool is not None and not _pool._closed:
        return _pool
    
    database_url = os.getenv('DATABASE_URL')
    
    # Fallback to config.json if DATABASE_URL is not set
    if not database_url:
        try:
            with open('config/config.json', 'r', encoding='utf-8') as f:
                config = json.load(f)
                database_url = config.get('database', {}).get('database_url')
                if not database_url:
                    logger.error("No database_url found in config/config.json")
                    raise ValueError("No database_url found in config/config.json")
                logger.info("Using database_url from config/config.json")
        except FileNotFoundError:
            logger.error("config/config.json not found")
            raise ValueError("config/config.json not found")
        except json.JSONDecodeError:
            logger.error("Invalid JSON in config.json")
            raise ValueError("Invalid JSON in config.json")
    
    # Validate URL format
    if not database_url or not database_url.startswith(('postgresql://', 'postgres://')):
        logger.error(f"Invalid database URL format: '{database_url}'. Must start with 'postgresql://' or 'postgres://'")
        logger.error("Please set DATABASE_URL in your .env file with the Transaction pooler URL:")
        logger.error("DATABASE_URL=postgresql://postgres.bnpqjqzviwgpgidbxqdt:[YOUR-PASSWORD]@aws-0-us-east-2.pooler.supabase.com:6543/postgres")
        raise ValueError("Invalid database URL format. Check your .env file.")
    
    # Enhanced debug logging for DNS resolution issues
    logger.info(f"Attempting to connect to database...")
    logger.debug(f"Database URL format: {database_url[:50]}...{database_url[-20:]}")  # Log partial URL for debugging
    
    # Extract hostname for DNS debugging
    import urllib.parse
    import re
    try:
        # Use regex to extract user, password, host, and port
        match = re.match(r"postgresql://([^:]+):([^@]+)@([^:]+):(\d+)/(.+)", database_url)
        if match:
            user, password, host, port, dbname = match.groups()
            logger.debug(f"Parsed DB components: user={user}, host={host}, port={port}, dbname={dbname}")
        else:
            logger.error("Could not parse database URL with regex.")

        parsed_url = urllib.parse.urlparse(database_url)
        hostname = parsed_url.hostname
        port = parsed_url.port
        logger.debug(f"Parsed hostname: {hostname}, port: {port}")
        
        # Test DNS resolution before attempting connection
        import socket
        try:
            ip_address = socket.gethostbyname(hostname)
            logger.debug(f"DNS resolution successful: {hostname} -> {ip_address}")
        except socket.gaierror as dns_error:
            logger.error(f"DNS resolution failed for {hostname}: {dns_error}")
            logger.error("This suggests a network connectivity issue or incorrect hostname")
            logger.error("Please check your internet connection and verify the hostname in DATABASE_URL")
            raise ConnectionError(f"DNS resolution failed for {hostname}: {dns_error}")
    except Exception as parse_error:
        logger.error(f"Failed to parse database URL: {parse_error}")
    
    for attempt in range(max_retries + 1):
        try:
            _pool = await asyncpg.create_pool(
                database_url,
                min_size=1,
                max_size=5,  # Reduced for transaction pooler
                command_timeout=30,  # Shorter timeout for transaction pooler
                statement_cache_size=0,  # Disable prepared statements for transaction pooler
                server_settings={
                    'application_name': 'discord_bot'
                }
            )
            
            # Test the connection
            async with _pool.acquire() as conn:
                await conn.execute('SELECT 1')
                
            logger.info("Database connection pool created successfully.")
            return _pool
            
        except asyncpg.PostgresError as e:
            logger.error(f"Database error on attempt {attempt + 1}: {e}")
            if attempt == max_retries:
                raise ConnectionError(f"Failed to connect to database after {max_retries + 1} attempts: {e}")
                
        except Exception as e:
            logger.error(f"Connection error on attempt {attempt + 1}: {type(e).__name__}: {e}")
            if attempt == max_retries:
                raise ConnectionError(f"Failed to connect to database after {max_retries + 1} attempts: {e}")
        
        if attempt < max_retries:
            logger.info(f"Retrying database connection in {retry_delay} seconds...")
            await asyncio.sleep(retry_delay)
            retry_delay *= 1.5  # Exponential backoff
    
    raise ConnectionError("Failed to establish database connection")

async def close_db_connection():
    """Closes the database connection pool."""
    global _pool
    if _pool:
        await _pool.close()
        _pool = None

# --- User Table Operations ---
async def get_user_data(user_id: int):
    """Fetches user data by user_id."""
    pool = await get_db_connection()
    async with pool.acquire() as conn:
        query = f"SELECT * FROM users WHERE user_id = {escape_sql_value(user_id)}"
        return await conn.fetchrow(query)

async def update_user_display_info(user_id: int, display_name: str, avatar_url: str):
    """Updates a user's display name and avatar URL."""
    pool = await get_db_connection()
    async with pool.acquire() as conn:
        query = f"""
            UPDATE users SET display_name = {escape_sql_value(display_name)}, 
                           avatar_url = {escape_sql_value(avatar_url)}, 
                           updated_at = NOW()
            WHERE user_id = {escape_sql_value(user_id)};
        """
        await conn.execute(query)

async def create_or_get_user(user_id: int, display_name: str = None, avatar_url: str = None, supabase_user_id: str = None):
    """Creates a new user or fetches existing user data, optionally updating display info and Supabase ID."""
    pool = await get_db_connection()
    async with pool.acquire() as conn:
        # Construct the INSERT statement dynamically based on provided fields
        columns = ["user_id"]
        values = [escape_sql_value(user_id)]
        update_set = ["updated_at = NOW()"]

        if display_name:
            columns.append("display_name")
            values.append(escape_sql_value(display_name))
            update_set.append(f"display_name = {escape_sql_value(display_name)}")
        if avatar_url:
            columns.append("avatar_url")
            values.append(escape_sql_value(avatar_url))
            update_set.append(f"avatar_url = {escape_sql_value(avatar_url)}")
        if supabase_user_id:
            columns.append("supabase_user_id")
            values.append(escape_sql_value(supabase_user_id))
            update_set.append(f"supabase_user_id = {escape_sql_value(supabase_user_id)}")

        insert_query = f"""
            INSERT INTO users ({', '.join(columns)})
            VALUES ({', '.join(values)})
            ON CONFLICT (user_id) DO UPDATE SET
                {', '.join(update_set)}
            RETURNING *;
        """
        return await conn.fetchrow(insert_query)

async def update_user_supabase_id(user_id: int, supabase_user_id: str):
    """Updates a user's Supabase Auth UUID."""
    pool = await get_db_connection()
    async with pool.acquire() as conn:
        query = f"""
            UPDATE users SET supabase_user_id = {escape_sql_value(supabase_user_id)}, updated_at = NOW()
            WHERE user_id = {escape_sql_value(user_id)};
        """
        await conn.execute(query)

async def update_user_solana_verified(user_id: int, wallet_address: str):
    """Updates a user's Solana verification status and wallet address."""
    pool = await get_db_connection()
    async with pool.acquire() as conn:
        query = f"""
            UPDATE users SET is_solana_verified = TRUE, wallet_address = {escape_sql_value(wallet_address)}, updated_at = NOW()
            WHERE user_id = {escape_sql_value(user_id)};
        """
        await conn.execute(query)

async def update_user_onboarded(user_id: int):
    """Marks a user as onboarded."""
    pool = await get_db_connection()
    async with pool.acquire() as conn:
        query = f"""
            UPDATE users SET is_onboarded = TRUE, updated_at = NOW()
            WHERE user_id = {escape_sql_value(user_id)};
        """
        await conn.execute(query)

async def get_all_verified_users():
    """Fetches all users who have verified their Solana wallet."""
    pool = await get_db_connection()
    async with pool.acquire() as conn:
        query = "SELECT user_id, wallet_address FROM users WHERE is_solana_verified = TRUE"
        return await conn.fetch(query)

async def check_user_verified_status(user_id: int):
    """Checks if a user has verified their Solana wallet."""
    pool = await get_db_connection()
    async with pool.acquire() as conn:
        query = f"SELECT is_solana_verified FROM users WHERE user_id = {escape_sql_value(user_id)}"
        result = await conn.fetchval(query)
        return result or False

# --- Verification Table Operations ---
async def insert_verification_token(token: str, user_id: int, expires_at: float):
    """Inserts a new verification token into the database."""
    pool = await get_db_connection()
    async with pool.acquire() as conn:
        query = f"""
            INSERT INTO verifications (token, user_id, expires_at)
            VALUES ({escape_sql_value(token)}, {escape_sql_value(user_id)}, to_timestamp({escape_sql_value(expires_at)}));
        """
        await conn.execute(query)

async def get_verification_token(token: str):
    """Fetches a verification token by its UUID."""
    pool = await get_db_connection()
    async with pool.acquire() as conn:
        query = f"SELECT * FROM verifications WHERE token = {escape_sql_value(token)}"
        return await conn.fetchrow(query)

async def update_verification_status(token: str, status: str):
    """Updates the status of a verification token."""
    pool = await get_db_connection()
    async with pool.acquire() as conn:
        query = f"""
            UPDATE verifications SET status = {escape_sql_value(status)} 
            WHERE token = {escape_sql_value(token)};
        """
        await conn.execute(query)

# --- XP System Operations ---
async def get_user_xp(user_id: int, guild_id: int = None):
    """Fetches a user's XP and level."""
    pool = await get_db_connection()
    async with pool.acquire() as conn:
        query = f"SELECT xp, level FROM users WHERE user_id = {escape_sql_value(user_id)}"
        return await conn.fetchrow(query)

async def update_user_xp(user_id: int, guild_id: int, xp: int, level: int):
    """Updates a user's XP and level."""
    pool = await get_db_connection()
    async with pool.acquire() as conn:
        query = f"""
            UPDATE users SET xp = {escape_sql_value(xp)}, 
                           level = {escape_sql_value(level)}, 
                           last_xp_gain_at = NOW(), 
                           updated_at = NOW()
            WHERE user_id = {escape_sql_value(user_id)};
        """
        await conn.execute(query)

async def get_xp_leaderboard_data(guild_id: str, limit: int = 10):
    """Fetches top users for the XP leaderboard."""
    pool = await get_db_connection()
    async with pool.acquire() as conn:
        query = f"SELECT user_id, display_name, xp, level FROM users WHERE is_solana_verified = true ORDER BY xp DESC LIMIT {escape_sql_value(limit)}"
        return await conn.fetch(query)

# --- Suggestions System Operations ---
async def insert_suggestion(message_id: int, channel_id: int, user_id: int, title: str, description: str):
    """Inserts a new suggestion into the database."""
    pool = await get_db_connection()
    async with pool.acquire() as conn:
        query = f"""
            INSERT INTO suggestions (message_id, channel_id, user_id, title, description)
            VALUES ({escape_sql_value(message_id)}, {escape_sql_value(channel_id)}, {escape_sql_value(user_id)}, {escape_sql_value(title)}, {escape_sql_value(description)})
            RETURNING suggestion_id;
        """
        return await conn.fetchval(query)

async def update_suggestion_votes(message_id: int, upvote: int = 0, downvote: int = 0):
    """Updates upvotes and downvotes for a suggestion."""
    pool = await get_db_connection()
    async with pool.acquire() as conn:
        query = f"""
            UPDATE suggestions SET upvotes = upvotes + {escape_sql_value(upvote)}, downvotes = downvotes + {escape_sql_value(downvote)}, last_reaction_at = NOW()
            WHERE message_id = {escape_sql_value(message_id)};
        """
        await conn.execute(query)


async def get_suggestion_by_message_id(message_id: int):
    """Fetches a suggestion by its Discord message ID."""
    pool = await get_db_connection()
    async with pool.acquire() as conn:
        query = f"SELECT * FROM suggestions WHERE message_id = {escape_sql_value(message_id)}"
        return await conn.fetchrow(query)

async def get_all_suggestions():
    """Fetches all suggestions."""
    pool = await get_db_connection()
    async with pool.acquire() as conn:
        query = "SELECT * FROM suggestions WHERE status != 'deleted' ORDER BY created_at DESC"
        return await conn.fetch(query)

async def delete_suggestion(message_id: int, deleted_by: int):
    """Marks a suggestion as deleted."""
    pool = await get_db_connection()
    async with pool.acquire() as conn:
        query = f"""
            UPDATE suggestions SET status = 'deleted', deleted_by = {escape_sql_value(deleted_by)} WHERE message_id = {escape_sql_value(message_id)};
        """
        await conn.execute(query)

async def update_suggestion_status(message_id: int, status: str, verified_by: int = None):
    """Updates the status of a suggestion (e.g., 'accepted')."""
    pool = await get_db_connection()
    async with pool.acquire() as conn:
        query = f"""
            UPDATE suggestions SET status = {escape_sql_value(status)}, verified_by = {escape_sql_value(verified_by)} WHERE message_id = {escape_sql_value(message_id)};
        """
        await conn.execute(query)

# --- Achievement System Operations ---
async def get_all_achievements():
    """Fetches all defined achievements and their criteria."""
    pool = await get_db_connection()
    async with pool.acquire() as conn:
        query = "SELECT * FROM achievements"
        return await conn.fetch(query)

async def insert_user_achievement(user_id: int, achievement_id: int):
    """Records that a user has earned an achievement."""
    pool = await get_db_connection()
    async with pool.acquire() as conn:
        query = f"""
            INSERT INTO user_achievements (user_id, achievement_id)
            VALUES ({escape_sql_value(user_id)}, {escape_sql_value(achievement_id)})
            ON CONFLICT (user_id, achievement_id) DO NOTHING;
        """
        await conn.execute(query)

async def delete_user_achievement(user_id: int, achievement_id: int):
    """Removes an achievement from a user."""
    pool = await get_db_connection()
    async with pool.acquire() as conn:
        query = f"""
            DELETE FROM user_achievements WHERE user_id = {escape_sql_value(user_id)} AND achievement_id = {escape_sql_value(achievement_id)};
        """
        await conn.execute(query)

async def check_user_has_achievement(user_id: int, achievement_id: int):
    """Checks if a user has a specific achievement."""
    pool = await get_db_connection()
    async with pool.acquire() as conn:
        query = f"""
            SELECT COUNT(*) FROM user_achievements WHERE user_id = {escape_sql_value(user_id)} AND achievement_id = {escape_sql_value(achievement_id)};
        """
        result = await conn.fetchval(query)
        return result > 0

async def get_user_achievements(user_id: int):
    """Fetches all achievements earned by a specific user."""
    pool = await get_db_connection()
    async with pool.acquire() as conn:
        query = f"""
            SELECT a.name, a.description, a.type
            FROM user_achievements ua
            JOIN achievements a ON ua.achievement_id = a.achievement_id
            WHERE ua.user_id = {escape_sql_value(user_id)};
        """
        return await conn.fetch(query)

# --- XP History Operations ---
async def insert_xp_history(user_id: str, current_xp: int, xp_change: int, new_xp: int, reason: str = None):
    """Records an XP change for a user."""
    try:
        pool = await get_db_connection()
        async with pool.acquire() as conn:
            # Convert user_id to integer for database compatibility
            user_id_int = int(user_id)
            
            query = f"""
                INSERT INTO xp_history (user_id, xp_change, new_xp, reason)
                VALUES ({escape_sql_value(user_id_int)}, {escape_sql_value(xp_change)}, {escape_sql_value(new_xp)}, {escape_sql_value(reason)});
            """
            await conn.execute(query)
    except Exception as e:
        logger.error(f"Error inserting XP history for user {user_id}: {e}")
        # Don't raise the exception to prevent breaking the main XP flow

# --- Message Logs Operations ---
async def insert_message_log(user_id: str, guild_id: str, channel_id: str, message_id: str, 
                             message_content: str, message_length: int, has_attachment: bool = None, has_link: bool = None):
    """Inserts a new message log entry."""
    pool = await get_db_connection()
    async with pool.acquire() as conn:
        # Calculate word count
        word_count = len(message_content.split()) if message_content else 0
        is_command = message_content.startswith('/') if message_content else False
        
        # Set unknown values to None
        sentiment_score = None
        reactions_count = 0  # Default to 0 as per database schema
        
        # Convert string IDs to integers for database compatibility
        user_id_int = int(user_id)
        guild_id_int = int(guild_id)
        channel_id_int = int(channel_id)
        message_id_int = int(message_id)
        
        query = f"""
            INSERT INTO message_logs (message_id, channel_id, guild_id, user_id, content_length, word_count, is_bot, is_command, sentiment_score, reactions_count)
            VALUES ({escape_sql_value(message_id_int)}, {escape_sql_value(channel_id_int)}, {escape_sql_value(guild_id_int)}, {escape_sql_value(user_id_int)}, 
                    {escape_sql_value(message_length)}, {escape_sql_value(word_count)}, false, {escape_sql_value(is_command)}, 
                    {escape_sql_value(sentiment_score)}, {escape_sql_value(reactions_count)});
        """
        await conn.execute(query)

# --- Voice Logs Operations ---
async def insert_voice_log(user_id: str, guild_id: str, channel_id: str, join_time, leave_time, duration_minutes: float):
    """Inserts a new voice log entry."""
    pool = await get_db_connection()
    async with pool.acquire() as conn:
        query = f"""
            INSERT INTO voice_logs (user_id, channel_id, guild_id, session_start, session_end, duration_minutes)
            VALUES ({escape_sql_value(user_id)}, {escape_sql_value(channel_id)}, {escape_sql_value(guild_id)}, 
                    {escape_sql_value(join_time.isoformat())}, {escape_sql_value(leave_time.isoformat())}, {escape_sql_value(int(duration_minutes))});
        """
        await conn.execute(query)

async def update_voice_log_end_time(log_id: str, session_end: float, duration_minutes: int):
    """Updates the end time and duration for a voice log entry."""
    pool = await get_db_connection()
    async with pool.acquire() as conn:
        query = f"""
            UPDATE voice_logs SET session_end = to_timestamp({escape_sql_value(session_end)}), duration_minutes = {escape_sql_value(duration_minutes)}
            WHERE id = {escape_sql_value(log_id)};
        """
        await conn.execute(query)

# --- User Daily Metrics Operations ---
async def upsert_user_daily_metrics(user_id: int, metric_date: str, messages_sent: int = 0,
                                    vc_minutes: int = 0, commands_used: int = 0, xp_gained: int = 0):
    """
    Inserts or updates daily metrics for a user.
    metric_date should be in 'YYYY-MM-DD' format.
    """
    pool = await get_db_connection()
    async with pool.acquire() as conn:
        query = f"""
            INSERT INTO user_daily_metrics (user_id, metric_date, messages_sent, vc_minutes, commands_used, xp_gained)
            VALUES ({escape_sql_value(user_id)}, {escape_sql_value(metric_date)}, {escape_sql_value(messages_sent)}, {escape_sql_value(vc_minutes)}, {escape_sql_value(commands_used)}, {escape_sql_value(xp_gained)})
            ON CONFLICT (user_id, metric_date) DO UPDATE SET
                messages_sent = user_daily_metrics.messages_sent + EXCLUDED.messages_sent,
                vc_minutes = user_daily_metrics.vc_minutes + EXCLUDED.vc_minutes,
                commands_used = user_daily_metrics.commands_used + EXCLUDED.commands_used,
                xp_gained = user_daily_metrics.xp_gained + EXCLUDED.xp_gained,
                updated_at = NOW();
        """
        await conn.execute(query)
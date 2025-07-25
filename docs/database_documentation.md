# Database Documentation

## Overview
The sendit Discord bot uses Supabase PostgreSQL with Transaction Pooler for scalable database operations. The system implements custom SQL escaping, comprehensive analytics tracking, and security features including Row-Level Security (RLS).

## Database Provider
- **Service**: Supabase PostgreSQL
- **Connection**: Transaction Pooler (port 6543)
- **Pool Mode**: Transaction-based pooling
- **Security**: Row-Level Security (RLS) enabled

## Connection Configuration

### Transaction Pooler Requirements
```python
await asyncpg.create_pool(
    database_url,
    min_size=1,
    max_size=5,  # Small pool for transaction pooler
    command_timeout=30,  # Short timeout for serverless
    statement_cache_size=0,  # REQUIRED: Disable prepared statements
    server_settings={'application_name': 'discord_bot'}
)
```

### Critical Configuration
- **Host**: `aws-0-us-east-2.pooler.supabase.com`
- **Port**: `6543` (Transaction pooler, NOT 5432)
- **Statement Cache**: MUST be disabled (`statement_cache_size=0`)
- **Connection Pool**: Maximum 5 connections for optimal performance

### Environment Variables

#### Container Environment
```env
# Docker container environment variable
DATABASE_URL=postgresql://postgres.[project-id]:[PASSWORD]@aws-0-us-east-2.pooler.supabase.com:6543/postgres

# Container-specific database settings
DATABASE_POOL_SIZE=5
DATABASE_POOL_MAX_OVERFLOW=10
DATABASE_POOL_TIMEOUT=30
```

#### Docker Compose Configuration
```yaml
services:
  sendit-bot:
    environment:
      - DATABASE_URL=${DATABASE_URL}
      - DATABASE_POOL_SIZE=5
      - DATABASE_POOL_MAX_OVERFLOW=10
    # Database connection managed within container
    networks:
      - sendit-network  # Isolated container network
```

## Security Implementation

### SQL Injection Prevention
Transaction pooler doesn't support prepared statements, so custom escaping is used:

```python
def escape_sql_value(value):
    if value is None:
        return 'NULL'
    elif isinstance(value, bool):
        return 'TRUE' if value else 'FALSE'
    elif isinstance(value, (int, float)):
        return str(value)
    elif isinstance(value, str):
        escaped = value.replace("'", "''")
        return f"'{escaped}'"
    else:
        escaped = str(value).replace("'", "''")
        return f"'{escaped}'"
```

### Query Pattern
```python
# ❌ Old Pattern (Parameterized - NOT supported)
await conn.execute("SELECT * FROM users WHERE user_id = $1", user_id)

# ✅ New Pattern (Escaped SQL - Transaction pooler compatible)
query = f"SELECT * FROM users WHERE user_id = {escape_sql_value(user_id)}"
await conn.execute(query)
```

## Database Schema

### Core Tables

#### users
Stores core user data, Discord information, and verification status.

```sql
CREATE TABLE users (
    user_id BIGINT PRIMARY KEY,
    display_name TEXT,
    avatar_url TEXT,
    is_solana_verified BOOLEAN DEFAULT FALSE,
    wallet_address TEXT,
    supabase_user_id UUID UNIQUE,
    is_onboarded BOOLEAN DEFAULT FALSE,
    xp INT DEFAULT 0,
    level INT DEFAULT 0,
    last_xp_gain_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_users_xp ON users (xp DESC);
CREATE INDEX idx_users_level ON users (level DESC);
CREATE INDEX idx_users_solana_verified ON users (is_solana_verified);
CREATE INDEX idx_users_supabase_user_id ON users (supabase_user_id);
```

#### verifications
Manages JWT tokens for wallet verification with expiration and status tracking.

```sql
CREATE TABLE verifications (
    token TEXT PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(user_id),
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
    status TEXT DEFAULT 'pending',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_verifications_user_id ON verifications (user_id);
CREATE INDEX idx_verifications_expires_at ON verifications (expires_at);
CREATE INDEX idx_verifications_status ON verifications (status);
```

#### suggestions
Community suggestion system with voting and moderation tracking.

```sql
CREATE TABLE suggestions (
    suggestion_id BIGINT PRIMARY KEY GENERATED BY DEFAULT AS IDENTITY,
    message_id BIGINT UNIQUE NOT NULL,
    channel_id BIGINT NOT NULL,
    user_id BIGINT NOT NULL REFERENCES users(user_id),
    title TEXT NOT NULL,
    description TEXT NOT NULL,
    upvotes INT DEFAULT 0,
    downvotes INT DEFAULT 0,
    status TEXT DEFAULT 'pending',
    deleted_by BIGINT,
    verified_by BIGINT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    last_reaction_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_suggestions_user_id ON suggestions (user_id);
CREATE INDEX idx_suggestions_status ON suggestions (status);
CREATE INDEX idx_suggestions_created_at ON suggestions (created_at DESC);
CREATE INDEX idx_suggestions_message_id ON suggestions (message_id);
```

### Analytics Tables

#### xp_history
Detailed transaction log for all XP changes with reasons and metadata.

```sql
CREATE TABLE xp_history (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id BIGINT NOT NULL REFERENCES users(user_id),
    xp_change INT NOT NULL,
    new_xp INT NOT NULL,
    reason TEXT,
    timestamp TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_xp_history_user_id ON xp_history (user_id);
CREATE INDEX idx_xp_history_timestamp ON xp_history (timestamp);
```

#### message_logs
Message metadata for activity analysis and content insights.

```sql
CREATE TABLE message_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    message_id BIGINT UNIQUE NOT NULL,
    channel_id BIGINT NOT NULL,
    guild_id BIGINT NOT NULL,
    user_id BIGINT NOT NULL REFERENCES users(user_id),
    timestamp TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    content_length INT,
    word_count INT,
    is_bot BOOLEAN DEFAULT FALSE,
    is_command BOOLEAN DEFAULT FALSE,
    sentiment_score FLOAT,
    reactions_count INT DEFAULT 0
);

CREATE INDEX idx_message_logs_user_id ON message_logs (user_id);
CREATE INDEX idx_message_logs_timestamp ON message_logs (timestamp);
CREATE INDEX idx_message_logs_channel_id ON message_logs (channel_id);
CREATE INDEX idx_message_logs_guild_id ON message_logs (guild_id);
```

#### voice_logs
Voice channel activity tracking for engagement metrics.

```sql
CREATE TABLE voice_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id BIGINT NOT NULL REFERENCES users(user_id),
    channel_id BIGINT NOT NULL,
    guild_id BIGINT NOT NULL,
    session_start TIMESTAMP WITH TIME ZONE NOT NULL,
    session_end TIMESTAMP WITH TIME ZONE,
    duration_minutes INT
);

CREATE INDEX idx_voice_logs_user_id ON voice_logs (user_id);
CREATE INDEX idx_voice_logs_session_start ON voice_logs (session_start);
CREATE INDEX idx_voice_logs_guild_id ON voice_logs (guild_id);
```

#### user_daily_metrics
Pre-aggregated daily statistics for dashboard performance optimization.

```sql
CREATE TABLE user_daily_metrics (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id BIGINT NOT NULL REFERENCES users(user_id),
    metric_date DATE NOT NULL,
    messages_sent INT DEFAULT 0,
    vc_minutes INT DEFAULT 0,
    commands_used INT DEFAULT 0,
    xp_gained INT DEFAULT 0,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE (user_id, metric_date)
);

CREATE INDEX idx_user_daily_metrics_user_id ON user_daily_metrics (user_id);
CREATE INDEX idx_user_daily_metrics_metric_date ON user_daily_metrics (metric_date);
```

### Achievement System Tables

#### achievements
Achievement definitions with flexible JSON criteria.

```sql
CREATE TABLE achievements (
    achievement_id INT PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    description TEXT NOT NULL,
    type TEXT NOT NULL,
    criteria JSONB
);
```

#### user_achievements
User-achievement relationships with earned timestamps.

```sql
CREATE TABLE user_achievements (
    user_id BIGINT NOT NULL REFERENCES users(user_id),
    achievement_id INT NOT NULL REFERENCES achievements(achievement_id),
    earned_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    PRIMARY KEY (user_id, achievement_id)
);

CREATE INDEX idx_user_achievements_user_id ON user_achievements (user_id);
CREATE INDEX idx_user_achievements_achievement_id ON user_achievements (achievement_id);
```

## Database Operations

### User Management
```python
# Create or get user with safe SQL escaping
async def create_or_get_user(user_id, display_name, avatar_url):
    query = f"""
    INSERT INTO users (user_id, display_name, avatar_url, created_at) 
    VALUES ({escape_sql_value(user_id)}, {escape_sql_value(display_name)}, 
            {escape_sql_value(avatar_url)}, NOW())
    ON CONFLICT (user_id) DO UPDATE SET 
        display_name = {escape_sql_value(display_name)},
        avatar_url = {escape_sql_value(avatar_url)},
        updated_at = NOW()
    """
```

### XP System Operations
```python
# Update user XP with level calculation
async def update_user_xp(user_id, guild_id, new_xp, new_level):
    query = f"""
    UPDATE users 
    SET xp = {escape_sql_value(new_xp)}, 
        level = {escape_sql_value(new_level)},
        last_xp_gain_at = NOW(),
        updated_at = NOW()
    WHERE user_id = {escape_sql_value(user_id)}
    """
```

### Suggestion System Operations
```python
# Insert new suggestion with return ID
async def insert_suggestion(message_id, channel_id, user_id, title, description):
    query = f"""
    INSERT INTO suggestions (message_id, channel_id, user_id, title, description)
    VALUES ({escape_sql_value(message_id)}, {escape_sql_value(channel_id)}, 
            {escape_sql_value(user_id)}, {escape_sql_value(title)}, 
            {escape_sql_value(description)})
    RETURNING suggestion_id
    """
```

## Error Handling

### Database Error Management
```python
async def handle_db_error(interaction, error, operation_name):
    """Handle database errors with user-friendly messages"""
    error_str = str(error).lower()
    
    if any(keyword in error_str for keyword in ['connection', 'timeout', 'network']):
        # Connection-related error
        user_message = "⚠️ Database Connection Issue - Please try again in a moment."
        log_level = "error"
    else:
        # General database error
        user_message = "⚠️ Database Error - Please try again later."
        log_level = "warning"
    
    logger.log(log_level, f"Database error during {operation_name}: {error}")
    
    if interaction:
        try:
            if interaction.response.is_done():
                await interaction.followup.send(user_message, ephemeral=True)
            else:
                await interaction.response.send_message(user_message, ephemeral=True)
        except Exception as e:
            logger.error(f"Failed to send error message to user: {e}")
    
    return True  # Indicates error was handled
```

### Common Error Patterns
- **Connection Timeout**: Network or pooler issues
- **Duplicate Key**: Constraint violations
- **Foreign Key**: Reference integrity issues
- **Data Type**: Type conversion errors

## Performance Optimization

### Indexing Strategy
- **Primary Keys**: Automatic clustered indexes
- **Foreign Keys**: Indexes on all foreign key columns
- **Query Patterns**: Indexes optimized for common queries
- **Timestamp Columns**: Indexes for time-based queries

### Connection Pooling
```python
# Optimal pool configuration for Transaction pooler
pool_config = {
    'min_size': 1,
    'max_size': 5,
    'command_timeout': 30,
    'statement_cache_size': 0,  # CRITICAL for Transaction pooler
    'server_settings': {'application_name': 'discord_bot'}
}
```

### Query Optimization
- **Batch Operations**: Daily metrics pre-aggregation
- **Efficient Joins**: Optimized table relationships
- **Selective Queries**: Only fetch required columns
- **Pagination**: Limit results for large datasets

## Monitoring and Maintenance

### Health Checks
```python
async def check_database_health():
    try:
        pool = await get_db_connection()
        async with pool.acquire() as conn:
            await conn.execute('SELECT 1')
        return {'status': 'healthy'}
    except Exception as e:
        return {'status': 'unhealthy', 'error': str(e)}
```

### Cleanup Tasks
```python
# Automated cleanup of expired verification tokens
@tasks.loop(minutes=30)
async def cleanup_expired_tokens():
    query = """
    UPDATE verifications 
    SET status = 'expired' 
    WHERE status = 'pending' AND expires_at < NOW()
    """
    
    # Delete very old records
    delete_query = """
    DELETE FROM verifications 
    WHERE created_at < NOW() - INTERVAL '7 days'
    """
```

### Performance Metrics
- **Query Response Times**: <100ms target for simple queries
- **Connection Pool Usage**: Monitor active connections
- **Index Efficiency**: Query plan analysis
- **Storage Growth**: Table size monitoring

## Backup and Recovery

### Data Protection
- **Supabase Backups**: Automatic daily backups
- **Point-in-time Recovery**: 30-day recovery window
- **Schema Versioning**: Track schema changes
- **Data Export**: Regular export capabilities

### Disaster Recovery
1. **Schema Recreation**: Automated schema deployment
2. **Data Restoration**: Point-in-time recovery
3. **Connection Testing**: Validate connectivity
4. **Data Validation**: Verify data integrity

## Migration Management

### Schema Updates
```sql
-- Example migration script
-- Migration: Add sentiment analysis to message_logs
-- Date: 2024-01-01
-- Author: Development Team

ALTER TABLE message_logs 
ADD COLUMN sentiment_score FLOAT;

CREATE INDEX idx_message_logs_sentiment 
ON message_logs (sentiment_score) 
WHERE sentiment_score IS NOT NULL;
```

### Version Control
- **Migration Scripts**: Sequential numbered migrations
- **Rollback Procedures**: Safe rollback mechanisms
- **Environment Sync**: Dev/staging/production alignment
- **Data Validation**: Post-migration verification

## Container-Specific Configuration

### Database Connection in Containers
```python
# Container-optimized connection pool
async def create_db_pool():
    pool = await asyncpg.create_pool(
        os.environ['DATABASE_URL'],
        min_size=int(os.environ.get('DATABASE_POOL_SIZE', 1)),
        max_size=int(os.environ.get('DATABASE_POOL_MAX_OVERFLOW', 5)),
        command_timeout=int(os.environ.get('DATABASE_POOL_TIMEOUT', 30)),
        statement_cache_size=0,  # Required for Supabase pooler
        server_settings={'application_name': 'sendit_discord_bot_container'}
    )
    return pool
```

### Container Health Checks
```bash
# Database connectivity check within container
docker exec sendit-bot python -c "
import asyncio
import asyncpg
import os

async def test_db():
    try:
        conn = await asyncpg.connect(os.environ['DATABASE_URL'])
        result = await conn.fetchval('SELECT 1')
        await conn.close()
        print('Database connection: OK')
        return True
    except Exception as e:
        print(f'Database connection failed: {e}')
        return False

asyncio.run(test_db())
"
```

### Container Resource Limits
```yaml
# docker-compose.yml database optimization
deploy:
  resources:
    limits:
      memory: 1G  # Affects connection pool size
      cpus: '1.0'
    reservations:
      memory: 512M  # Minimum for database operations
      cpus: '0.5'
```

## Troubleshooting

### Container-Specific Issues

#### Container Database Connection Failure
```
docker exec sendit-bot: database connection failed
```
**Solutions**:
- Verify DATABASE_URL environment variable in container
- Check container network connectivity
- Ensure Supabase allows connections from container IP
- Validate container DNS resolution

#### Container Resource Constraints
```
Container killed due to memory limit
```
**Solutions**:
- Increase memory limits in docker-compose.yml
- Optimize DATABASE_POOL_SIZE for available memory
- Monitor container memory usage with `docker stats`

### Common Database Issues

#### DuplicatePreparedStatementError
```
asyncpg.exceptions.DuplicatePreparedStatementError: prepared statement already exists
```
**Solution**: Ensure `statement_cache_size=0` in connection pool

#### Connection Timeout in Container
```
asyncpg.exceptions.ConnectionTimeoutError
```
**Solutions**:
- Check container network connectivity
- Verify Supabase pooler status
- Validate DATABASE_URL format in container environment
- Ensure container has internet access

#### Invalid Database URL in Container
```
Invalid database URL format
```
**Solution**: Use correct Transaction pooler URL in container environment:
```
postgresql://postgres.bnpqjqzviwgpgidbxqdt:[PASSWORD]@aws-0-us-east-2.pooler.supabase.com:6543/postgres
```

### Debugging Tools
- **Query Logging**: Enable detailed query logs
- **Connection Monitoring**: Track pool usage
- **Performance Analysis**: Query execution plans
- **Error Aggregation**: Centralized error reporting

## Security Best Practices

### Access Control
- **Least Privilege**: Minimal required permissions
- **Connection Encryption**: TLS encryption required
- **Secret Management**: Secure credential storage
- **Audit Logging**: Complete access logging

### Data Protection
- **Input Validation**: Comprehensive validation
- **SQL Injection**: Custom escaping functions
- **Data Masking**: Sensitive data protection
- **Encryption**: At-rest and in-transit encryption

### Compliance
- **GDPR Compliance**: User data protection
- **Data Retention**: Configurable retention policies
- **Right to Deletion**: Data deletion procedures
- **Audit Trails**: Complete operation logging
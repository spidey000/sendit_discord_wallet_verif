#!/bin/bash
set -e

# Docker entrypoint script for Sendit Discord Bot
echo "🚀 Starting Sendit Discord Bot container..."
echo "📅 $(date)"
echo "🔧 Running as user: $(whoami)"
echo "📂 Working directory: $(pwd)"

# Function to log with timestamp
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1"
}

# Validate required environment variables
validate_env() {
    local missing_vars=()
    
    # Required variables
    if [ -z "$DISCORD_TOKEN" ]; then
        missing_vars+=("DISCORD_TOKEN")
    fi
    
    if [ -z "$DATABASE_URL" ]; then
        missing_vars+=("DATABASE_URL")
    fi
    
    if [ -z "$JWT_SECRET" ]; then
        missing_vars+=("JWT_SECRET")
    fi
    
    # Check if any required variables are missing
    if [ ${#missing_vars[@]} -ne 0 ]; then
        log "❌ Missing required environment variables:"
        for var in "${missing_vars[@]}"; do
            log "   - $var"
        done
        log "💡 Please ensure all required variables are set in your .env file or container environment"
        exit 1
    fi
    
    log "✅ All required environment variables are set"
}

# Validate JWT secret strength
validate_jwt_secret() {
    if [ ${#JWT_SECRET} -lt 32 ]; then
        log "⚠️  WARNING: JWT_SECRET should be at least 32 characters long for security"
        log "   Current length: ${#JWT_SECRET}"
    fi
    
    # Check if it's still the default test value
    if [[ "$JWT_SECRET" == *"test_secret"* ]] || [[ "$JWT_SECRET" == *"replace_this"* ]]; then
        log "❌ JWT_SECRET appears to be a default test value"
        log "💡 Please generate a secure random JWT secret"
        exit 1
    fi
    
    log "✅ JWT_SECRET validation passed"
}

# Create necessary directories
setup_directories() {
    log "📁 Setting up directories..."
    
    # Create logs directory if it doesn't exist
    if [ ! -d "/app/logs" ]; then
        mkdir -p /app/logs
        log "✅ Created logs directory"
    fi
    
    # Create backups directory if it doesn't exist  
    if [ ! -d "/app/backups" ]; then
        mkdir -p /app/backups
        log "✅ Created backups directory"
    fi
    
    # Ensure proper permissions
    if [ -w "/app/logs" ] && [ -w "/app/backups" ]; then
        log "✅ Directory permissions are correct"
    else
        log "⚠️  Warning: May not have write permissions for logs/backups"
    fi
}

# Check database connectivity
check_database() {
    log "🔗 Testing database connectivity..."
    
    # Extract host from DATABASE_URL for basic connectivity test
    DB_HOST=$(echo "$DATABASE_URL" | sed -n 's/.*@\([^:]*\).*/\1/p')
    
    if [ -n "$DB_HOST" ]; then
        # Simple connectivity test (if nc/netcat is available)
        if command -v nc >/dev/null 2>&1; then
            if nc -z "$DB_HOST" 6543 2>/dev/null; then
                log "✅ Database host is reachable"
            else
                log "⚠️  Warning: Cannot reach database host $DB_HOST:6543"
                log "   This may be normal if the database requires authentication"
            fi
        else
            log "ℹ️  Skipping network connectivity test (nc not available)"
        fi
    fi
}

# Health check function
health_check() {
    log "🏥 Performing health checks..."
    
    # Check Python version
    python_version=$(python --version 2>&1)
    log "🐍 $python_version"
    
    # Check disk space
    if command -v df >/dev/null 2>&1; then
        disk_usage=$(df -h /app | tail -1 | awk '{print "Used: " $3 " Available: " $4 " (" $5 " full)"}')
        log "💾 Disk space: $disk_usage"
    fi
    
    # Check memory
    if [ -r "/proc/meminfo" ]; then
        mem_total=$(grep MemTotal /proc/meminfo | awk '{print int($2/1024) " MB"}')
        mem_available=$(grep MemAvailable /proc/meminfo | awk '{print int($2/1024) " MB"}')
        log "🧠 Memory: Total $mem_total, Available $mem_available"
    fi
}

# Wait for dependencies (if any)
wait_for_dependencies() {
    log "⏳ Waiting for dependencies..."
    
    # Wait a few seconds for any external services to be ready
    sleep 3
    log "✅ Dependency wait completed"
}

# Cleanup function for graceful shutdown
cleanup() {
    log "🛑 Received shutdown signal, cleaning up..."
    
    # Kill background processes if any
    if [ ! -z "$BACKGROUND_PID" ]; then
        kill $BACKGROUND_PID 2>/dev/null || true
    fi
    
    log "👋 Shutdown complete"
    exit 0
}

# Set up signal handlers for graceful shutdown
trap cleanup SIGTERM SIGINT

# Main execution
main() {
    log "🔍 Starting pre-flight checks..."
    
    # Run all validation checks
    validate_env
    validate_jwt_secret
    setup_directories
    check_database
    health_check
    wait_for_dependencies
    
    log "✅ All pre-flight checks passed!"
    log "🚀 Starting Discord bot application..."
    
    # Execute the main command
    exec "$@"
}

# If script is being executed directly (not sourced)
if [ "${BASH_SOURCE[0]}" == "${0}" ]; then
    main "$@"
fi
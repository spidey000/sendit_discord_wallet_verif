# Multi-stage build for optimized Discord bot container
# Stage 1: Build environment with wheels
FROM python:3.11-slim as builder

# Install only essential build dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    gcc \
    libc6-dev \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Create optimized virtual environment
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy requirements first for better caching
COPY requirements.txt .

# Build wheels and install dependencies with optimization
RUN pip install --no-cache-dir --upgrade pip wheel && \
    pip wheel --no-cache-dir --wheel-dir /opt/wheels -r requirements.txt && \
    pip install --no-cache-dir --find-links /opt/wheels -r requirements.txt && \
    find /opt/venv -name "*.pyc" -delete && \
    find /opt/venv -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true && \
    find /opt/venv -name "*.pyo" -delete && \
    find /opt/venv -name "test*" -type d -exec rm -rf {} + 2>/dev/null || true && \
    find /opt/venv -name "*test*" -name "*.py" -delete 2>/dev/null || true && \
    rm -rf /opt/venv/lib/python*/site-packages/pip /opt/venv/lib/python*/site-packages/setuptools

# Stage 2: Minimal runtime environment
FROM python:3.11-slim

# Install only essential runtime dependencies
RUN apt-get update && apt-get install -y \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean \
    && rm -rf /var/cache/apt/* \
    && rm -rf /usr/share/man/* \
    && rm -rf /usr/share/doc/* \
    && rm -rf /usr/share/locale/* \
    && rm -rf /usr/share/info/* \
    && rm -rf /var/log/* \
    && rm -rf /tmp/* \
    && find /usr/lib -name "*.pyc" -delete \
    && find /usr/lib -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true

# Create non-root user for security
RUN groupadd -g 1000 senditbot && \
    useradd -r -u 1000 -g senditbot senditbot

# Copy virtual environment from builder stage
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
ENV PYTHONPATH="/app:$PYTHONPATH"

# Set working directory
WORKDIR /app

# Copy application files (optimized selection)
COPY --chown=senditbot:senditbot main.py config/ health_check.py cogs/ utils/ ./
COPY --chown=senditbot:senditbot docker-entrypoint.sh /usr/local/bin/

# Create necessary directories
RUN mkdir -p logs backups && \
    chown -R senditbot:senditbot logs backups

# Set executable permissions
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

# Switch to non-root user
USER senditbot

# Health check using Python (no curl dependency)
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD python health_check.py

# Expose port
EXPOSE ${PORT:-8080}

# Set entrypoint
ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]
CMD ["python", "main.py"]
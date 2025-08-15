FROM ubuntu:22.04

WORKDIR /app

# Install system dependencies including Python, ffmpeg, Docker CLI, and Playwright dependencies
RUN apt-get update && apt-get install -y \
    python3.11 \
    python3-pip \
    curl \
    ca-certificates \
    net-tools \
    procps \
    ffmpeg \
    apt-transport-https \
    gnupg \
    lsb-release \
    # Playwright system dependencies for browser automation
    libnspr4 \
    libnss3 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libatspi2.0-0 \
    libxcomposite1 \
    libxdamage1 \
    libxrandr2 \
    libgtk-3-0 \
    libxss1 \
    libasound2 \
    libdrm2 \
    libxkbcommon0 \
    libgbm1 \
    && curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /usr/share/keyrings/docker-archive-keyring.gpg \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/docker-archive-keyring.gpg] https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" | tee /etc/apt/sources.list.d/docker.list > /dev/null \
    && apt-get update \
    && apt-get install -y docker-ce-cli docker-compose-plugin \
    && rm -rf /var/lib/apt/lists/*

# Download and install SimpleX Chat CLI
RUN curl -L https://github.com/simplex-chat/simplex-chat/releases/download/v6.4.2/simplex-chat-ubuntu-22_04-x86_64 -o /usr/local/bin/simplex-chat \
    && chmod +x /usr/local/bin/simplex-chat

# Download and install XFTP CLI
RUN curl -L https://github.com/simplex-chat/simplexmq/releases/latest/download/xftp-ubuntu-22_04-x86_64 -o /usr/local/bin/xftp \
    && chmod +x /usr/local/bin/xftp

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN python3 -m pip install --no-cache-dir -r requirements.txt

# Copy bot code and scripts
COPY bot.py .
COPY simplex_utils.py .
COPY config_manager.py .
COPY xftp_client.py .
COPY file_download_manager.py .
COPY message_handler.py .
COPY websocket_manager.py .
COPY check_connection.sh .
COPY websocket_connect.py .
COPY connect.sh .

# Copy platform service architecture files
COPY platform_services.py .

# Copy additional bot modules
COPY admin_manager.py .
COPY invite_manager.py .
COPY message_context.py .

# Create a non-root user and add to docker group
RUN groupadd -r appuser && useradd -r -g appuser appuser \
    && groupadd -f -g 959 docker \
    && usermod -aG docker appuser

# Create logs directory and set permissions
RUN mkdir -p /app/logs /app/media /app/temp /app/temp/xftp && \
    chown -R 1000:1001 /app

# Install Playwright browser binaries to accessible location
ENV PLAYWRIGHT_BROWSERS_PATH=/app/.cache/ms-playwright
RUN mkdir -p /app/.cache/ms-playwright && \
    chown -R 1000:1001 /app/.cache && \
    python3 -m playwright install chromium && \
    chown -R 1000:1001 /app/.cache

# Make scripts executable
RUN chmod +x check_connection.sh connect.sh

# Run the bot (user will be set via docker-compose)
CMD ["python", "bot.py"]
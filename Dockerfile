FROM python:3.11-slim

WORKDIR /app

# Install system dependencies including terminal support
RUN apt-get update && apt-get install -y \
    curl \
    ca-certificates \
    net-tools \
    procps \
    && rm -rf /var/lib/apt/lists/*

# Download and install SimpleX Chat CLI
RUN curl -L https://github.com/simplex-chat/simplex-chat/releases/latest/download/simplex-chat-ubuntu-22_04-x86-64 -o /usr/local/bin/simplex-chat \
    && chmod +x /usr/local/bin/simplex-chat

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy bot code and scripts
COPY bot.py .
COPY simplex_utils.py .
COPY connect_invitation.sh .
COPY check_connection.sh .
COPY websocket_connect.py .
COPY connect.sh .

# Create logs directory
RUN mkdir -p /app/logs

# Make scripts executable
RUN chmod +x connect_invitation.sh check_connection.sh connect.sh

# Run the bot
CMD ["python", "bot.py"]
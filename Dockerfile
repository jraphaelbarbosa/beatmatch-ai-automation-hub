FROM node:18.16.0-bookworm-slim

# Install system dependencies, python3, pip, git, and curl
RUN apt-get update && apt-get install -y \
    python3 \
    python3-pip \
    python3-venv \
    python3-dev \
    build-essential \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

# Upgrade pip to enable modern wheels
RUN pip3 install --no-cache-dir --upgrade pip --break-system-packages

# Install python requirements globally inside the container (Debian Bookworm needs --break-system-packages)
RUN pip3 install --no-cache-dir --break-system-packages \
    spotipy \
    sqlalchemy \
    psycopg2-binary \
    playwright \
    apify-client \
    python-dotenv \
    pandas \
    pyyaml \
    flask \
    redis \
    requests

# Install Playwright Chromium browser and its system dependencies
RUN playwright install chromium
RUN playwright install-deps chromium

# Install n8n globally (compilation of isolated-vm succeeds on Node 18.16.0!)
RUN npm install -g n8n@latest

# Create a node user home directory and set permissions
RUN mkdir -p /home/node/.n8n && chown -R node:node /home/node

# Set environment variables
ENV N8N_PORT=5678
ENV HOME=/home/node
WORKDIR /home/node

USER node

EXPOSE 5678

CMD ["n8n", "start"]

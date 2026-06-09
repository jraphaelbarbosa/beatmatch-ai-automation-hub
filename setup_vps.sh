#!/bin/bash
# ==============================================================================
# BeatMatchAI Automation Hub - Google Compute Engine VPS Setup Script
# Target OS: Ubuntu 22.04 LTS / 24.04 LTS
# ==============================================================================

# Exit immediately if any command fails
set -e

echo "======================================================================"
echo "🚀 Starting VPS Provisioning: n8n + Python Co-location Environment"
echo "======================================================================"

# 1. Update system packages
echo "[*] Updating system repositories..."
sudo apt update && sudo apt upgrade -y

# 2. Install essential runtimes and tools
echo "[*] Installing Git, Python3, pip, venv, Curl, and system libraries..."
sudo apt install -y git python3 python3-pip python3-venv curl build-essential libssl-dev

# 3. Install Node.js (needed for running n8n globally on host)
echo "[*] Installing Node.js LTS (v20)..."
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt install -y nodejs

# Verify runtimes
echo "[OK] Node.js Version: $(node -v)"
echo "[OK] NPM Version: $(npm -v)"
echo "[OK] Python Version: $(python3 --version)"

# 4. Install n8n and PM2 globally
echo "[*] Installing n8n and PM2 Process Manager globally..."
sudo npm install -g pm2 n8n --unsafe-perm

# 5. Set up Python Virtual Environment in the project directory
echo "[*] Provisioning local Python virtual environment (venv)..."
if [ ! -d "venv" ]; then
    python3 -m venv venv
fi

# Activate virtualenv and install pip requirements
echo "[*] Installing Python packages from requirements.txt..."
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

# 6. Install Playwright browsers and system dependencies
echo "[*] Installing Playwright Chromium browser and OS libraries..."
playwright install chromium
sudo venv/bin/playwright install-deps chromium

echo "[OK] All runtimes and dependencies successfully installed!"

# 7. Configure PM2 to keep n8n running in the background
echo "[*] Registering n8n with PM2 process manager..."
# Check if n8n is already running under PM2
if pm2 list | grep -q "n8n"; then
    echo "[*] n8n is already registered. Restarting process..."
    pm2 restart n8n
else
    echo "[*] Starting n8n in background on port 5678..."
    pm2 start n8n --name "n8n" -- --port 5678
fi

# Enable PM2 startup script to restart processes on VM reboot
echo "[*] Saving PM2 state and generating startup scripts..."
pm2 save
sudo env PATH=$PATH:/usr/bin pm2 startup systemd -u $USER --hp $HOME

echo "======================================================================"
echo "🎉 VPS PROVISIONING COMPLETED SUCCESSFULLY!"
echo "======================================================================"
echo "👉 Next steps to finalize setup:"
echo "  1. Copy your environment variables to a '.env' file:"
echo "     cp .env.example .env"
echo "     nano .env"
echo "  2. Run database and Monday.com setup scripts:"
echo "     source venv/bin/activate"
echo "     python src/utils/db_setup.py"
echo "     python src/utils/monday_setup.py"
echo "  3. Open n8n in your browser (http://<your-vm-ip>:5678) and import:"
echo "     n8n/workflow_unified_beatmatch.json"
echo "======================================================================"

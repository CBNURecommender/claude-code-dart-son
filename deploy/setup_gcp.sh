#!/bin/bash
set -euo pipefail

# Configuration
APP_DIR="/opt/dart-noti-bot"
SERVICE_NAME="dart-noti-bot"
CURRENT_USER="$(whoami)"

echo "=== DART Notification Bot - GCP Setup ==="

# 1. Install system dependencies
echo "[1/6] Installing system dependencies..."
sudo apt-get update -y
sudo apt-get install -y python3-venv python3-pip

# 2. Copy application files
echo "[2/6] Setting up application directory..."
sudo mkdir -p "$APP_DIR"
sudo cp -r ./* "$APP_DIR/"
sudo chown -R "$CURRENT_USER:$CURRENT_USER" "$APP_DIR"

# 3. Create virtual environment
echo "[3/6] Creating virtual environment..."
cd "$APP_DIR"
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

# 4. Create data directory
echo "[4/6] Creating data directory..."
mkdir -p "$APP_DIR/data"

# 5. Setup systemd service
echo "[5/6] Configuring systemd service..."
sudo sed -e "s|__USER__|$CURRENT_USER|g" \
         -e "s|__WORKDIR__|$APP_DIR|g" \
         "$APP_DIR/deploy/dart-noti-bot.service" \
    | sudo tee /etc/systemd/system/$SERVICE_NAME.service > /dev/null
sudo systemctl daemon-reload
sudo systemctl enable $SERVICE_NAME

# 6. Check .env file
echo "[6/6] Checking configuration..."
if [ ! -f "$APP_DIR/.env" ]; then
    echo ""
    echo "⚠️  .env file not found!"
    echo "   Create $APP_DIR/.env with the following variables:"
    echo "   DART_API_KEY=your_key"
    echo "   TELEGRAM_BOT_TOKEN=your_token"
    echo "   TELEGRAM_CHAT_ID=your_chat_id"
    echo ""
    echo "   Then run: sudo systemctl start $SERVICE_NAME"
else
    echo "✅ .env file found"
    echo ""
    echo "To start the service:"
    echo "   sudo systemctl start $SERVICE_NAME"
    echo "   sudo systemctl status $SERVICE_NAME"
fi

echo ""
echo "=== Setup complete ==="
echo "Useful commands:"
echo "   Test telegram: cd $APP_DIR && source venv/bin/activate && python main.py test-telegram"
echo "   Add company:   cd $APP_DIR && source venv/bin/activate && python main.py add \"삼성전자\""
echo "   View logs:     journalctl -u $SERVICE_NAME -f"

#!/usr/bin/env bash
# ==============================================================================
# Computer Lab Management - Linux Lab Agent Setup Script
# ==============================================================================
# Usage:
#   chmod +x deploy/linux/setup_agent.sh
#   ./deploy/linux/setup_agent.sh
# ==============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

echo "=========================================================="
echo "  Computer Lab Management - Linux Agent Setup"
echo "=========================================================="
echo "[1/5] Working directory: $PROJECT_ROOT"
cd "$PROJECT_ROOT"

# 1. Check Python 3.12+
echo "[2/5] Checking Python installation..."
if command -v python3 >/dev/null 2>&1; then
    PYTHON_BIN="python3"
elif command -v python >/dev/null 2>&1; then
    PYTHON_BIN="python"
else
    echo "ERROR: Python 3 was not found. Please install Python 3.12+ (e.g. sudo apt install python3 python3-venv python3-pip)"
    exit 1
fi
echo "      Detected: $($PYTHON_BIN --version)"

# 2. Setup Virtual Environment
echo "[3/5] Setting up virtual environment at .venv..."
if [ ! -d ".venv" ]; then
    $PYTHON_BIN -m venv .venv
fi
VENV_PYTHON="$PROJECT_ROOT/.venv/bin/python"
VENV_PIP="$PROJECT_ROOT/.venv/bin/pip"

# 3. Install Dependencies
echo "[4/5] Installing Python dependencies..."
"$VENV_PIP" install --upgrade pip --quiet
"$VENV_PIP" install -r requirements.txt --quiet
echo "      Dependencies installed."

# 4. Configure agent.env
echo "[5/5] Configuring agent environment (agent.env)..."
ENV_FILE="$PROJECT_ROOT/agent.env"

if [ ! -f "$ENV_FILE" ]; then
    echo ""
    echo "Enter Central Lab Server Configuration:"
    read -rp "Server LAN URL [http://127.0.0.1:8000]: " SERVER_URL_INPUT
    SERVER_URL_INPUT="${SERVER_URL_INPUT:-http://127.0.0.1:8000}"

    read -rp "Agent Enrollment Token (LAB_AGENT_TOKEN): " TOKEN_INPUT
    TOKEN_INPUT="${TOKEN_INPUT:-replace-with-same-agent-enrollment-secret-from-server}"

    cat <<EOF > "$ENV_FILE"
# Computer Lab Management - Agent Configuration for Linux
LAB_SERVER_URL=$SERVER_URL_INPUT
LAB_AGENT_TOKEN=$TOKEN_INPUT
LAB_HEARTBEAT_INTERVAL=5.0
LAB_POWER_DRY_RUN=true
LAB_SCREEN_CAPTURE_INTERVAL=0.5
LAB_SCREEN_IMAGE_QUALITY=70
LAB_SCREEN_MAX_WIDTH=1920
LAB_SCREEN_MAX_HEIGHT=1080
LAB_SCREEN_MAX_FRAME_RATE=2.0
EOF
    # Restrict file permissions to owner only (read/write)
    chmod 600 "$ENV_FILE"
    echo "      Created $ENV_FILE with restricted permissions (600)"
else
    echo "      Found existing $ENV_FILE"
fi

echo ""
echo "=========================================================="
echo "  Setup Complete! To start the lab agent manually:"
echo "    source .venv/bin/activate"
echo "    set -a && source agent.env && set +a"
echo "    python -m agent.main"
echo ""
echo "  To install as a background systemd service:"
echo "    See deploy/linux/lab-agent.service"
echo "=========================================================="


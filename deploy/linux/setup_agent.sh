#!/usr/bin/env bash
# ==============================================================================
# Computer Lab Management - Linux Lab Agent Setup Script
# ==============================================================================
# Usage:
#   chmod +x deploy/linux/setup_agent.sh
#   ./deploy/linux/setup_agent.sh
#
# Safe to re-run: an existing virtual environment (.venv) and agent.env are
# reused. This script does NOT auto-install a systemd service; see the printed
# instructions and deploy/linux/lab-agent.service for manual installation.
# ==============================================================================

set -euo pipefail

# ---------------------------------------------------------------------------
# Resolve absolute project root. Quoting is used throughout so this remains
# safe even when the repository lives at a path containing spaces (e.g.
# "/run/media/akash/New Volume/DC Project/LabManagement").
# ---------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
VENV_DIR="${PROJECT_ROOT}/.venv"
VENV_PYTHON="${VENV_DIR}/bin/python"
ENV_FILE="${PROJECT_ROOT}/agent.env"
REQUIREMENTS_FILE="${PROJECT_ROOT}/requirements.txt"

echo "=========================================================="
echo "  Computer Lab Management - Linux Agent Setup"
echo "=========================================================="
echo "[1/5] Working directory: ${PROJECT_ROOT}"
cd "${PROJECT_ROOT}"

# ---------------------------------------------------------------------------
# 1. Check Python 3.12+
# ---------------------------------------------------------------------------
echo "[2/5] Checking Python installation..."
PYTHON_BIN=""
if command -v python3 >/dev/null 2>&1; then
    PYTHON_BIN="python3"
elif command -v python >/dev/null 2>&1; then
    PYTHON_BIN="python"
else
    echo "ERROR: Python 3 was not found. Please install Python 3.12+ (e.g. sudo apt install python3 python3-venv python3-pip)"
    exit 1
fi

echo "      Detected: $("${PYTHON_BIN}" --version 2>&1)"

if ! PYTHON_VERSION_INFO="$("${PYTHON_BIN}" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")' 2>/dev/null)"; then
    echo "ERROR: Could not determine the Python version from '${PYTHON_BIN}'."
    exit 1
fi
PYTHON_MAJOR="${PYTHON_VERSION_INFO%%.*}"
PYTHON_MINOR="${PYTHON_VERSION_INFO#*.}"
if [ "${PYTHON_MAJOR}" -lt 3 ] || { [ "${PYTHON_MAJOR}" -eq 3 ] && [ "${PYTHON_MINOR}" -lt 12 ]; }; then
    echo "ERROR: Python 3.12+ is required. Detected ${PYTHON_VERSION_INFO}."
    echo "       Please install Python 3.12 or newer."
    exit 1
fi

# ---------------------------------------------------------------------------
# 2. Setup / reuse the virtual environment
# ---------------------------------------------------------------------------
echo "[3/5] Setting up virtual environment at ${VENV_DIR}..."
if [ ! -d "${VENV_DIR}" ]; then
    echo "      Creating virtual environment..."
    if ! "${PYTHON_BIN}" -m venv "${VENV_DIR}"; then
        echo "ERROR: Failed to create the virtual environment at:"
        echo "       ${VENV_DIR}"
        echo "       Ensure the 'venv' module is available (e.g. sudo apt install python3-venv)."
        exit 1
    fi
else
    echo "      Existing virtual environment found - reusing it."
fi

# Verify the virtual environment's Python executable actually exists.
if [ ! -x "${VENV_PYTHON}" ]; then
    echo "ERROR: The virtual environment Python executable was not found:"
    echo "       ${VENV_PYTHON}"
    echo "       The virtual environment appears to be broken."
    echo "       Remove '${VENV_DIR}' and re-run this script."
    exit 1
fi
echo "      Using Python: ${VENV_PYTHON}"
"${VENV_PYTHON}" --version

# ---------------------------------------------------------------------------
# 3. Ensure pip is available inside the virtual environment
# ---------------------------------------------------------------------------
echo "      Checking pip availability..."
if ! "${VENV_PYTHON}" -m pip --version >/dev/null 2>&1; then
    echo "      pip not found in the virtual environment - bootstrapping with ensurepip..."
    if ! "${VENV_PYTHON}" -m ensurepip --upgrade; then
        echo "ERROR: Failed to bootstrap pip inside the virtual environment."
        echo "       Try removing '${VENV_DIR}' and re-running, or install python3-venv."
        exit 1
    fi
    echo "      pip bootstrap complete."
fi

# ---------------------------------------------------------------------------
# 4. Install dependencies
# ---------------------------------------------------------------------------
echo "[4/5] Installing Python dependencies..."
if [ ! -f "${REQUIREMENTS_FILE}" ]; then
    echo "ERROR: requirements.txt not found at:"
    echo "       ${REQUIREMENTS_FILE}"
    exit 1
fi

if ! "${VENV_PYTHON}" -m pip install --upgrade pip --quiet; then
    echo "ERROR: Failed to upgrade pip inside the virtual environment."
    exit 1
fi
if ! "${VENV_PYTHON}" -m pip install -r "${REQUIREMENTS_FILE}" --quiet; then
    echo "ERROR: Failed to install dependencies from:"
    echo "       ${REQUIREMENTS_FILE}"
    exit 1
fi
echo "      Dependencies installed."

# ---------------------------------------------------------------------------
# 5. Configure agent.env
# ---------------------------------------------------------------------------
echo "[5/5] Configuring agent environment (agent.env)..."
if [ ! -f "${ENV_FILE}" ]; then
    echo ""
    echo "Enter Central Lab Server Configuration:"
    read -rp "Server LAN URL [http://127.0.0.1:8000]: " SERVER_URL_INPUT
    SERVER_URL_INPUT="${SERVER_URL_INPUT:-http://127.0.0.1:8000}"

    read -rp "Agent Enrollment Token (LAB_AGENT_TOKEN): " TOKEN_INPUT
    TOKEN_INPUT="${TOKEN_INPUT:-replace-with-same-agent-enrollment-secret-from-server}"

    cat <<EOF > "${ENV_FILE}"
# Computer Lab Management - Agent Configuration for Linux
LAB_SERVER_URL=${SERVER_URL_INPUT}
LAB_AGENT_TOKEN=${TOKEN_INPUT}
LAB_HEARTBEAT_INTERVAL=5.0
LAB_POWER_DRY_RUN=true
LAB_SCREEN_CAPTURE_INTERVAL=0.5
LAB_SCREEN_IMAGE_QUALITY=70
LAB_SCREEN_MAX_WIDTH=1920
LAB_SCREEN_MAX_HEIGHT=1080
LAB_SCREEN_MAX_FRAME_RATE=2.0
EOF
    # Restrict file permissions to owner only (read/write)
    chmod 600 "${ENV_FILE}"
    echo "      Created ${ENV_FILE} with restricted permissions (600)"
else
    echo "      Found existing ${ENV_FILE}"
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
echo "    (Paths containing spaces are quoted in the service template.)"
echo "=========================================================="

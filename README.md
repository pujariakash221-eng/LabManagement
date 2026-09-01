# Computer Lab Management Platform

A modern, secure, lightweight Computer Laboratory Management System designed for college computer labs and local networks.

---

## 🏛️ System Architecture

```text
+-----------------------------------------------------------------------+
|                         LAB SERVER (FastAPI)                          |
|                  Host: 0.0.0.0  |  Default Port: 8000                 |
|             Dashboard: http://<SERVER_LAN_IP>:8000/                   |
+-----------------------------------+-----------------------------------+
                                    |
                  College Lab Local Area Network (LAN)
                                    |
        +---------------------------+---------------------------+
        |                           |                           |
+-------v-------------+     +-------v-------------+     +-------v-------------+
|   LAB-PC-01 (Win)   |     |  LAB-PC-02 (Linux)  |     |   LAB-PC-N (Win)    |
| Agent (Task/Service)|     |   Agent (systemd)   |     | Agent (Task/Service)|
+---------------------+     +---------------------+     +---------------------+
```

### Core Components
- **Central Server (FastAPI)**: Serves the web dashboard, manages agent registration, processes heartbeats, coordinates power operations, scans LAN devices, and relays real-time screen streams via WebSockets.
- **Client Agent (Python)**: Runs as a background service on lab workstations, reports hardware/OS telemetry, broadcasts compressed JPEG screen frames (read-only), and executes structured power commands (shutdown/restart).
- **SQLite Database**: Persists user accounts (scrypt-hashed), registered agent records, and security audit trails.
- **Web Dashboard**: Clean, responsive operator console built with semantic HTML, CSS custom properties, and vanilla JS.

---

## 📋 System Requirements

- **Python**: Python 3.12 or newer.
- **Operating Systems**:
  - **Server**: Linux, macOS, or Windows.
  - **Workstations**: Windows 10/11, Linux (Ubuntu/Debian with X11/Wayland), or macOS.
- **Python Dependencies** (`requirements.txt`):
  - `fastapi`, `uvicorn[standard]`, `httpx`, `Pillow`, `websockets`, `itsdangerous`.
- **Linux Workstation Prerequisites**:
  ```bash
  sudo apt-get install python3-tk python3-dev
  ```

---

## 🚀 Server Deployment & Setup

### Step 1: Clone and Create Virtual Environment
```bash
cd LabManagement
python3 -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
pip install --upgrade pip
pip install -r requirements.txt
```

### Step 2: Configure Environment Variables
Copy `.env.example` to `.env` or set environment variables:
```bash
cp .env.example .env
```

Generate strong secrets for the application:
```bash
python3 -c "import secrets; print('LAB_APP_SECRET=' + secrets.token_urlsafe(48))"
python3 -c "import secrets; print('LAB_AGENT_ENROLLMENT_SECRET=' + secrets.token_urlsafe(48))"
```

Edit `.env` and set:
```bash
# Server Bind Configuration
LAB_SERVER_HOST=0.0.0.0
LAB_SERVER_PORT=8000

# Generated Security Secrets
LAB_APP_SECRET=<generated_app_secret_at_least_32_chars>
LAB_AGENT_ENROLLMENT_SECRET=<generated_agent_secret_at_least_24_chars>

# Administrator Credentials (created automatically on initial boot)
LAB_INITIAL_ADMIN_USERNAME=admin
LAB_INITIAL_ADMIN_PASSWORD=SetYourStrongAdminPasswordHere

# Security & Safety Settings
LAB_POWER_DRY_RUN=true
LAB_SECURE_COOKIES=false    # Set true if deploying behind HTTPS
LAB_DATABASE_PATH=labmanagement.sqlite3
```

### Step 3: Find the Server LAN IP Address
The client agents need the server's LAN IP address to connect:
- **Linux**: `hostname -I | awk '{print $1}'` or `ip addr show`
- **Windows**: `ipconfig` (look for IPv4 Address on Ethernet / Wi-Fi)
- **macOS**: `ipconfig getifaddr en0`

*Example Server LAN IP: `192.168.1.100`*

### Step 4: Start the Central Server
```bash
# Using Python module entrypoint:
set -a && source .env && set +a  # Linux/macOS
python -m server.main

# Or using Uvicorn directly:
uvicorn server.main:app --host 0.0.0.0 --port 8000
```

Verify server health:
```bash
curl http://127.0.0.1:8000/api/health
# Returns: {"status": "running"}
```

Access the Web Dashboard in your browser:
- Local: `http://localhost:8000/`
- From another LAN PC: `http://192.168.1.100:8000/`

---

## 💻 Workstation Agent Installation

Deploy the client agent on each lab computer. The agent automatically creates a persistent hardware ID in `~/.lab_management/agent_id`.

### A. Windows Workstations (PowerShell / Batch)

1. Copy the `LabManagement` project folder to the target Windows computer (e.g. `C:\LabManagement`).
2. Open PowerShell as Administrator and run the automated setup script:
   ```powershell
   Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
   cd C:\LabManagement
   .\deploy\windows\setup_agent.ps1
   ```
3. The script will:
   - Verify Python 3.12+ installation.
   - Create `.venv` and install `requirements.txt`.
   - Prompt for `LAB_SERVER_URL` (e.g. `http://192.168.1.100:8000`) and `LAB_AGENT_TOKEN`.
   - Test connectivity to the central server.
   - Create `agent.env`.
4. **Manual Run**:
   ```cmd
   .\deploy\windows\start_agent.bat
   ```
5. **Automated Windows Startup**:
   - Create a shortcut to `deploy\windows\start_agent.bat` and place it in the Windows Startup folder:
     `shell:startup` (press `Win + R` and type `shell:startup`).
   - Or register a Windows Scheduled Task to run on system boot.

---

### B. Linux Workstations (systemd Service)

1. Copy the project to `/opt/labmanagement` on the workstation.
2. Run the automated Linux setup script:
   ```bash
   cd /opt/labmanagement
   chmod +x deploy/linux/setup_agent.sh
   ./deploy/linux/setup_agent.sh
   ```
3. Install and enable the systemd service:
   ```bash
   # Configure your local user in deploy/linux/lab-agent.service if different from 'labuser'
   sudo cp deploy/linux/lab-agent.service /etc/systemd/system/
   sudo systemctl daemon-reload
   sudo systemctl enable lab-agent.service
   sudo systemctl start lab-agent.service
   ```
4. Check agent service status and logs:
   ```bash
   sudo systemctl status lab-agent.service
   journalctl -u lab-agent.service -f
   ```

---

### C. macOS Workstations (launchd Daemon)

1. Place project in `/Users/Shared/LabManagement`.
2. Configure `agent.env` with `LAB_SERVER_URL` and `LAB_AGENT_TOKEN`.
3. Load the launchd plist:
   ```bash
   cp deploy/macos/com.labmanagement.agent.plist ~/Library/LaunchAgents/
   launchctl load ~/Library/LaunchAgents/com.labmanagement.agent.plist
   launchctl start com.labmanagement.agent
   ```

---

## 🔍 Step-by-Step Verification Guide

### 1. Dashboard Sign-In
1. Navigate to `http://<SERVER_LAN_IP>:8000/`.
2. Enter the initial admin credentials (`admin` / configured password).
3. Verify that the topbar displays the `ADMIN` badge and the live pulse indicator shows `🟢 Server Connected`.

### 2. Workstation Registration & Heartbeat
1. Once an agent starts on a lab PC, it registers with `POST /api/agents/register` and sends periodic heartbeats every 5 seconds.
2. Observe the **Computer Inventory** table on the dashboard:
   - The workstation appears with its hostname, IP address, OS, and status `🟢 ONLINE`.
   - The Summary Cards reflect the live `Total` and `Online` computer counts.

### 3. Workstation Details & Multi-Field Search
1. Click on any workstation row to open the **Workstation Details** panel.
2. Verify hardware metadata, IP address, and click the copy icon to copy the unique `Agent ID`.
3. Use the search bar to filter by hostname, IP address, OS, or Agent ID.
4. Toggle status filter tabs (`All`, `Online`, `Offline`).

### 4. Live Remote Screen Viewing
1. In the computer table or details panel, click **📺 View Live Screen**.
2. The Screen Viewer modal opens and establishes a WebSocket stream with the agent.
3. Verify live desktop screen frames rendered in the viewport.
4. Press `Escape` or click `✕` to close the screen session.

### 5. Local Subnet Network Discovery
1. In the **Network Discovery** section, click **Scan Network**.
2. The server sweeps the local `/24` subnet using bounded ICMP ping probes.
3. Active LAN devices are listed separately from registered managed workstations.

### 6. Power Operations in Dry-Run Mode
1. Ensure `LAB_POWER_DRY_RUN=true` on both server and agent.
2. Select an ONLINE workstation in the dashboard and click **Shutdown** or **Restart**.
3. The confirmation dialog opens with a clear warning and workstation details. Click **Confirm**.
4. The power command is queued (`202 Accepted`).
5. The agent fetches the command, logs the simulated action (`dry_run=True`), and acknowledges the outcome without shutting down the system.
6. The event is recorded in the **Activity & Audit Log**.

### 7. Transitioning from Dry-Run to Production
Before enabling real OS power commands:
1. Verify laboratory firewall and authorization policies.
2. Ensure the agent runs with permissions to invoke system power commands (Windows `shutdown.exe`, Linux `systemctl poweroff/reboot`, macOS `shutdown`).
3. Set `LAB_POWER_DRY_RUN=false` in `.env` on the server and `agent.env` on all trusted lab agents.
4. Restart the server and agent services.

---

## 🛡️ Role-Based Access Control (RBAC)

| Role | Workstation Inventory | Screen Viewing | Network Discovery | Shutdown / Restart | Activity & Audit Logs |
| :--- | :---: | :---: | :---: | :---: | :---: |
| **VIEWER** | ✅ | ✅ | ✅ | ❌ | ❌ |
| **OPERATOR** | ✅ | ✅ | ✅ | ✅ | ❌ |
| **ADMIN** | ✅ | ✅ | ✅ | ✅ | ✅ |

- **Server-Side Authorization**: Role requirements are enforced at every API endpoint. Unauthorized requests return `HTTP 403 Forbidden` and log security audit events.
- **Session Expiry**: Sessions are stored in signed, HttpOnly cookies. Expired sessions automatically redirect to `/login?reason=expired`.

---

## 🔒 Security Best Practices

1. **Secret Management**:
   - `LAB_APP_SECRET` and `LAB_AGENT_ENROLLMENT_SECRET` must be long, random strings (32+ characters).
   - Never commit `.env` or `agent.env` files to git repository.
2. **Network Perimeter**:
   - Restrict port 8000 to the private laboratory subnet using host firewall rules (e.g. `ufw`, `iptables`, Windows Defender Firewall).
   - Do not expose the server directly to the public internet.
3. **Production HTTPS**:
   - When deploying in production, place the FastAPI server behind a reverse proxy (such as Nginx or Caddy) with TLS/HTTPS.
   - Set `LAB_SECURE_COOKIES=true` in `.env`.
4. **Least-Privilege Execution**:
   - Run the server and agent under dedicated non-root service accounts.
   - Database files (`labmanagement.sqlite3`) are created with restrictive file permissions (`0600`).
5. **Audit Logging & Redaction**:
   - All authentication attempts, authorization denials, screen streams, and power actions are recorded with timestamps.
   - Passwords, agent enrollment tokens, session IDs, and screen frames are **never** logged.

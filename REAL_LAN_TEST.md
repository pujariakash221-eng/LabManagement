# Real LAN Deployment & Verification Guide

This guide details how to perform a real deployment test of the **Computer Lab Management Platform** across multiple physical computers on a local area network (LAN).

---

## 🏛️ Deployment Topology

```text
+-------------------------------------------------------------------------+
|                  CENTRAL LAB SERVER (Linux / Windows / macOS)           |
|  - IP: <SERVER_LAN_IP> (e.g. 192.168.1.100)                             |
|  - Port: 8000 (TCP)                                                     |
|  - Web Dashboard: http://<SERVER_LAN_IP>:8000/                          |
+------------------------------------+------------------------------------+
                                     |
                         College Lab Network / LAN Subnet
                                     |
          +--------------------------+--------------------------+
          |                                                     |
+---------v-------------------------+         +-----------------v-------------------------+
|   WORKSTATION 1 (Windows 10/11)   |         |      WORKSTATION 2 (Linux Ubuntu/Debian)  |
| - IP: 192.168.1.150               |         | - IP: 192.168.1.151                       |
| - Runs: Windows Agent Service     |         | - Runs: systemd lab-agent.service         |
+-----------------------------------+         +-------------------------------------------+
```

---

## 1. Central Server Setup

### 1.1 Find the Server's LAN IP Address
Run the appropriate command on your server machine:
- **Linux**: `hostname -I | awk '{print $1}'` or `ip -4 addr show`
- **Windows**: `ipconfig` (look for *IPv4 Address* under Ethernet or Wi-Fi)
- **macOS**: `ipconfig getifaddr en0`

*Example Detected Server LAN IP: `192.168.1.100`*

### 1.2 Verify Server Configuration (`.env`)
Ensure `.env` contains:
```ini
LAB_SERVER_HOST=0.0.0.0
LAB_SERVER_PORT=8000
LAB_POWER_DRY_RUN=true
```

### 1.3 Start the Central Server
```bash
source .venv/bin/activate
python -m server.main
```
Verify local health:
```bash
curl http://127.0.0.1:8000/api/health
# Response: {"status": "running"}
```

---

## 2. Firewall Requirements

For client workstations to communicate with the central server, port **8000 (TCP)** must be open on the server machine's firewall.

### On Linux Server (UFW / iptables):
```bash
# Allow incoming port 8000 from local subnet (e.g. 192.168.1.0/24)
sudo ufw allow 8000/tcp
# Or allow only from private LAN:
sudo ufw allow from 192.168.1.0/24 to any port 8000 proto tcp
```

### On Windows Server (Windows Defender Firewall):
```powershell
New-NetFirewallRule -DisplayName "Lab Management Server (Port 8000)" `
  -Direction Inbound -LocalPort 8000 -Protocol TCP -Action Allow
```

---

## 3. Client Workstation Setup

### 3.1 Setup on a Second Windows PC

1. **Copy Project Directory**:
   Copy the `LabManagement` folder to `C:\LabManagement` on the target Windows machine.

2. **Run Automated Setup (PowerShell)**:
   Open PowerShell and run:
   ```powershell
   Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
   cd C:\LabManagement
   .\deploy\windows\setup_agent.ps1
   ```
   When prompted:
   - **Server LAN URL**: Enter `http://<SERVER_LAN_IP>:8000` (e.g., `http://192.168.1.100:8000`).
   - **Agent Token**: Enter the `LAB_AGENT_ENROLLMENT_SECRET` from the server's `.env`.

3. **Start the Agent**:
   ```cmd
   .\deploy\windows\start_agent.bat
   ```

---

### 3.2 Setup on a Second Linux PC

1. **Copy Project Directory**:
   Copy the `LabManagement` folder to `/opt/labmanagement` on the target Linux machine.

2. **Run Setup Script**:
   ```bash
   cd /opt/labmanagement
   chmod +x deploy/linux/setup_agent.sh
   ./deploy/linux/setup_agent.sh
   ```
   When prompted, enter:
   - **Server LAN URL**: `http://<SERVER_LAN_IP>:8000`
   - **Agent Token**: `LAB_AGENT_TOKEN` matching the server's secret.

3. **Start Manually or as a Service**:
   ```bash
   # Option A: Manual test
   source .venv/bin/activate
   set -a && source agent.env && set +a
   python -m agent.main

   # Option B: Systemd service
   sudo cp deploy/linux/lab-agent.service /etc/systemd/system/
   sudo systemctl daemon-reload
   sudo systemctl enable --now lab-agent.service
   ```

---

## 4. Verification Checklist

### Step 1: Workstation Registration
- Open `http://<SERVER_LAN_IP>:8000/` in a web browser from any computer on the LAN.
- Log in with the admin credentials from `.env`.
- In the **Computer Inventory** table, verify that the second PC appears with its correct **Hostname**, **IP Address**, **OS**, and a green badge: `🟢 ONLINE`.

### Step 2: Live Heartbeat & Offline Detection
- Watch the **Last Seen** column update every 5 seconds.
- Stop the agent on the client PC (`Ctrl+C`).
- Within ~15 seconds (configured `LAB_OFFLINE_TIMEOUT`), verify that the workstation badge transitions to `🔴 OFFLINE`.
- Restart the agent; verify that status returns to `🟢 ONLINE`.

### Step 3: Remote Screen Streaming
- In the dashboard, click **📺 View Live Screen** for the client PC.
- Verify the modal opens and renders live JPEG screen frames captured from the client PC.
- Close the modal with `Escape` or the close button; verify the stream terminates cleanly.

### Step 4: Network Discovery Scan
- In the dashboard, click **Scan Network**.
- Verify that the server scans the `/24` LAN subnet and lists active network devices.
- Confirm discovered devices remain in the separate Discovery list and do not mutate registered workstation inventory.

### Step 5: Role-Based Authorization
- **VIEWER**: Can monitor inventory, view details, and watch screen streams. Cannot trigger power operations or view audit logs.
- **OPERATOR**: Can monitor, view screens, and execute dry-run power actions. Cannot view audit logs or admin status.
- **ADMIN**: Has access to all controls, including the **Activity & Audit Log**.

### Step 6: Safe Dry-Run Power Operations
- With `LAB_POWER_DRY_RUN=true` on both server and agent:
- Click **Shutdown** or **Restart** on an ONLINE computer.
- Review and confirm the action modal.
- The agent receives the command, outputs:
  ```text
  Received power command 'restart' (id: ..., dry_run=True)
  Power action 'restart' executed with result: dry_run
  Acknowledged power command ... (result=dry_run)
  ```
- Verify the client PC **does not** actually shut down or reboot.
- In the **Activity & Audit Log**, verify the corresponding `POWER_RESTART_REQUEST` and `POWER_RESTART_SUCCESS` events.

---

## 5. Troubleshooting Commands

### Server unreachable from Client PC:
1. Ping the server from the client:
   ```cmd
   ping <SERVER_LAN_IP>
   ```
2. Test HTTP health endpoint with PowerShell or curl:
   ```powershell
   Invoke-RestMethod -Uri http://<SERVER_LAN_IP>:8000/api/health
   ```
   ```bash
   curl http://<SERVER_LAN_IP>:8000/api/health
   ```
3. Check if server process is listening on `0.0.0.0:8000`:
   ```bash
   ss -tulpn | grep 8000
   ```
4. Verify firewall allows TCP port 8000 on the server.

### Agent fails authentication (`401 Unauthorized`):
- Ensure `LAB_AGENT_TOKEN` in `agent.env` on the client PC matches `LAB_AGENT_ENROLLMENT_SECRET` in `.env` on the server.

### Screen streaming blank or failed:
- On Linux client PCs, ensure X11/Wayland display server is active (`export DISPLAY=:0`).
- Ensure `Pillow` is installed in the agent's virtual environment:
  ```bash
  .venv/bin/pip install Pillow
  ```

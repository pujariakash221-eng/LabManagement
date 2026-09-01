# Manual LAN Test Procedure
## Computer Lab Management Platform - Windows Release Testing

This document contains **exact step-by-step procedures** for testing the LabManagement system across multiple machines on a local area network (LAN) after switching to Windows environment.

**Equipment Needed:**
- Server PC (Windows/Linux) - runs the central FastAPI server
- At least 1 Workstation PC (Windows) - runs the lab agent
- Network connectivity between both machines on the same subnet
- Administrator access on Windows systems
- Approximately 30-45 minutes for complete test cycle

---

## PHASE A: SERVER PC SETUP

### Step A1: Find Server LAN IP Address

**On Windows Server PC:**
1. Open Command Prompt (`cmd.exe`) or PowerShell
2. Run:
   ```cmd
   ipconfig
   ```
3. Look for your network adapter (Ethernet or Wi-Fi)
4. Find the `IPv4 Address` line (typically `192.168.x.x` or `10.x.x.x`)
5. **Record this IP** - you will need it on workstation agents

**Example Output:**
```
Ethernet adapter Local Area Connection:
   Connection-specific DNS Suffix: example.com
   IPv4 Address: 192.168.1.100
   Subnet Mask: 255.255.255.0
```

**Your Server IP: _____________** (write it down)

### Step A2: Verify Project Files

On the server PC, verify the LabManagement project is properly copied:
```cmd
cd LabManagement
dir
```

Expected files/folders: `server`, `agent`, `dashboard`, `deploy`, `tests`, `.env.example`, `requirements.txt`, `README.md`

### Step A3: Create .env Configuration File

1. Open `.env.example` in a text editor
2. Copy its contents and create a new file called `.env`
3. Set strong secrets:
   ```bash
   python -c "import secrets; print('APP_SECRET: ' + secrets.token_urlsafe(48))"
   python -c "import secrets; print('ENROLLMENT_SECRET: ' + secrets.token_urlsafe(48))"
   ```
4. Edit `.env` with these values:
   ```
   LAB_SERVER_HOST=0.0.0.0
   LAB_SERVER_PORT=8000
   LAB_APP_SECRET=<generated_secret_from_python>
   LAB_AGENT_ENROLLMENT_SECRET=<generated_secret_from_python>
   LAB_INITIAL_ADMIN_USERNAME=admin
   LAB_INITIAL_ADMIN_PASSWORD=TestLab2025!
   LAB_POWER_DRY_RUN=true
   LAB_SECURE_COOKIES=false
   LAB_DATABASE_PATH=labmanagement.sqlite3
   ```

### Step A4: Start the Central Server

**Option 1: PowerShell (Recommended for Windows)**
```powershell
cd d:\DC Project\LabManagement
python -m server.main
```

**Option 2: Command Prompt**
```cmd
cd d:\DC Project\LabManagement
python -m server.main
```

Expected output:
```
INFO:     Uvicorn running on http://0.0.0.0:8000
INFO:     Application startup complete
```

### Step A5: Verify Server Health (On Server PC)

Open a browser and navigate to:
```
http://localhost:8000/api/health
```

**Expected Response:**
```json
{"status": "running"}
```

### Step A6: Verify Dashboard Accessibility

Navigate to:
```
http://localhost:8000/
```

**Expected Result:**
- Redirects to `/login` page
- Login form displays with username/password fields
- Page title shows "Lab Management - Login"

---

## PHASE B: WINDOWS LAB PC SETUP

### Step B1: Install Python 3.12 (if not already installed)

1. On the lab workstation, download Python from https://www.python.org/downloads/
2. Run the installer
3. **Important**: Check "Add Python to PATH"
4. Complete installation

Verify installation:
```cmd
python --version
```

Should output: `Python 3.12.x` or newer

### Step B2: Copy/Obtain LabManagement Project

Copy the `LabManagement` project folder to the workstation PC. Example path:
```
C:\LabManagement
```

Verify files exist:
```cmd
cd C:\LabManagement
dir
```

### Step B3: Run Windows Agent Setup Script

1. Open **PowerShell as Administrator**
2. Navigate to the project:
   ```powershell
   cd C:\LabManagement
   Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
   ```
3. Run the setup script:
   ```powershell
   .\deploy\windows\setup_agent.ps1
   ```

The script will prompt for:
- **Server LAN URL**: Enter the IP from Step A1
  - Example: `http://192.168.1.100:8000`
- **Agent Enrollment Token**: Enter the `LAB_AGENT_ENROLLMENT_SECRET` from `.env` on server
  - Must match exactly

### Step B4: Start the Lab Agent

**Option 1: Batch File (Easiest)**
```cmd
cd C:\LabManagement
.\deploy\windows\start_agent.bat
```

**Option 2: Direct Python**
```cmd
cd C:\LabManagement
set /p LAB_SERVER_URL=<.env
set /p LAB_AGENT_TOKEN=<.env
python -m agent.main
```

**Expected Output from Agent:**
```
2026-09-01 16:30:45 INFO Agent initialization starting...
2026-09-01 16:30:46 INFO Connected to server http://192.168.1.100:8000
2026-09-01 16:30:46 INFO Agent registered: xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
2026-09-01 16:30:46 INFO Heartbeat sent successfully
2026-09-01 16:30:51 INFO Heartbeat sent successfully
```

---

## PHASE C: DASHBOARD LOGIN & CONNECTIVITY TEST

### Step C1: Access Dashboard from Server PC

On the **server PC**, open a web browser:
```
http://localhost:8000/
```

### Step C2: Perform Initial Login

- Username: `admin` (or your configured LAB_INITIAL_ADMIN_USERNAME)
- Password: `TestLab2025!` (or your configured LAB_INITIAL_ADMIN_PASSWORD)
- Click **Sign In**

**Expected Result:**
- Dashboard loads successfully
- Top-right corner shows: `👤 admin` and `ADMIN` badge (green/blue)
- Server status shows: `🟢 Connected`
- Computers section is visible

### Step C3: Verify Workstation Appears Online

1. Look at the **Computer Inventory** table
2. Your lab PC should appear with:
   - Status: `🟢 ONLINE` (green)
   - Hostname: (your PC name)
   - IP Address: (visible)
   - Operating System: `Windows`
   - Last Heartbeat: (just now)

**If workstation does NOT appear:**
- Check agent error messages on workstation console
- Verify network connectivity: `ping 192.168.1.100` from lab PC
- Verify enrollment token matches exactly
- Check server logs for connection errors

### Step C4: Verify Summary Cards

Check top-right summary cards display:
- **Total**: 1
- **Online**: 1
- **Offline**: 0
- **Discovered**: (may vary)

---

## PHASE D: HEARTBEAT & OFFLINE DETECTION TEST

### Step D1: Verify Initial Heartbeat

1. Workstation is ONLINE in dashboard
2. Observe for 10 seconds - no action needed
3. **Expected**: Status remains `🟢 ONLINE`

### Step D2: Stop the Agent to Trigger Offline State

1. On the **lab workstation**, stop the agent:
   - Press `Ctrl+C` in the terminal running the agent
   - Or close the `start_agent.bat` window
2. Note the time

### Step D3: Wait for Offline Detection

1. Return to dashboard on **server PC**
2. Wait up to 20 seconds
3. Workstation status should change to: `🔴 OFFLINE`
4. Summary card "Offline" count increases to 1

**Note:** Timeout configured in `.env`: `LAB_OFFLINE_TIMEOUT=15.0` seconds

### Step D4: Restart Agent and Verify Online Again

1. On lab workstation, restart agent:
   ```cmd
   .\deploy\windows\start_agent.bat
   ```
2. Watch dashboard
3. Within 5 seconds, status should return to: `🟢 ONLINE`

**Test Result: [✓] PASS / [ ] FAIL**

---

## PHASE E: SCREEN VIEWING TEST

### Step E1: Open Screen Viewer

1. On dashboard (server PC), click on the workstation row
2. Details panel opens on right side
3. Click **📺 View Live Screen** button

### Step E2: Verify WebSocket Connection

Expected sequence:
1. Screen modal opens
2. Status shows: "Connecting..."
3. After 1-2 seconds: "Connected (Waiting for frames)"
4. After a few more seconds: "● LIVE STREAM" (with pulsing dot)

### Step E3: Verify Live Frames

1. Desktop screenshot should appear in the modal
2. Perform action on lab PC (move mouse, open notepad, etc.)
3. Dashboard updates with new frames
4. Frames update every ~0.5-1 second

**Timing Note:** `LAB_SCREEN_CAPTURE_INTERVAL=0.5` in `.env` controls capture frequency

### Step E4: Close Screen Viewer

1. Press `Escape` or click the `✕` close button
2. Modal closes
3. Server logs show: "Screen viewer disconnected"

**Test Result: [✓] PASS / [ ] FAIL**

---

## PHASE F: NETWORK DISCOVERY TEST

### Step F1: Run Network Scan

1. On dashboard, scroll to **Network Discovery** section
2. Click **Scan Network** button
3. Button shows "Scanning subnet..." with spinner

### Step F2: Wait for Scan to Complete

Scan duration: 5-15 seconds (depending on subnet size and host responsiveness)

### Step F3: Review Discovered Devices

**Expected Results:**
- List shows active devices on local `/24` subnet
- Each device shows:
  - IP Address
  - Hostname (if available via reverse DNS)
  - Status: "Discovered Endpoint"
- Your registered workstation appears in this list (separate from the Inventory)

### Step F4: Verify Discovered vs Registered

- **Discovered devices**: Any active IP on subnet (not necessarily registered)
- **Registered agents**: Only PCs running the LabManagement agent

**Test Result: [✓] PASS / [ ] FAIL**

---

## PHASE G: POWER OPERATIONS (DRY-RUN MODE) TEST

**SAFETY REMINDER:** `LAB_POWER_DRY_RUN=true` means NO ACTUAL shutdown occurs - only simulated.

### Step G1: Queue a Shutdown Command

1. Dashboard workstation details panel
2. Click **⏻ Shutdown** button
3. Confirmation dialog opens
4. Message shows:
   - "Confirm Computer Shutdown"
   - "Are you sure you want to shut down workstation..."
   - **Warning**: "This will immediately power off the selected workstation..."

### Step G2: Confirm Shutdown Command

1. Click **Shut Down Workstation** button (red)
2. Button shows "Queueing..." with spinner
3. Toast notification: "Shutdown command successfully queued for [hostname]"

### Step G3: Verify Agent Receives Command

1. Check the **lab workstation console** running the agent
2. Agent should log:
   ```
   2026-09-01 16:35:20 INFO Received power command: shutdown
   2026-09-01 16:35:20 INFO DRY RUN - Would execute: shutdown -s -t 60
   2026-09-01 16:35:20 INFO Command acknowledgement sent
   ```

### Step G4: Verify System Does NOT Shutdown

1. Lab workstation remains **powered on and responsive**
2. System has NOT actually shut down
3. This confirms dry-run mode is active ✓

### Step G5: Test Restart Command

1. Return to dashboard
2. Click **↻ Restart** button
3. Confirm restart in dialog
4. Agent logs show:
   ```
   2026-09-01 16:35:30 INFO Received power command: restart
   2026-09-01 16:35:30 INFO DRY RUN - Would execute: shutdown -r -t 60
   2026-09-01 16:35:30 INFO Command acknowledgement sent
   ```
5. System remains running (dry-run only)

**Test Result: [✓] PASS / [ ] FAIL**

---

## PHASE H: PERSISTENCE TEST

### Step H1: Restart the Central Server

1. On **server PC**, stop the FastAPI server:
   - Press `Ctrl+C` in the running server terminal
2. Wait 5 seconds for graceful shutdown
3. Restart the server:
   ```cmd
   python -m server.main
   ```

### Step H2: Verify Data Persistence

Expected behavior after restart:
- Dashboard loads normally
- **Same admin account exists** (does not require re-setup)
- **Workstation registration persists**:
  - Lab PC still appears in inventory
  - Agent details (hostname, IP, OS) preserved
  - Agent ID unchanged
- **Audit logs persist**:
  - All power commands logged previously still visible
  - Login history preserved

### Step H3: Verify Agent Continues Working

1. Lab workstation agent continues running
2. Sends heartbeats to restarted server
3. Status updates to `🟢 ONLINE` within 5 seconds
4. Screen viewing still works

**Test Result: [✓] PASS / [ ] FAIL**

---

## PHASE I: RBAC ENFORCEMENT TEST

This phase tests role-based access control boundaries.

### Step I1: Test VIEWER Role Restrictions

1. Dashboard top menu → Create/Invite a VIEWER account:
   - (If available in UI, or manually via database)
2. Log out (current ADMIN session)
3. Log in as VIEWER user
4. Verify VIEWER **CAN**:
   - View workstation inventory ✓
   - View workstation details ✓
   - View live screen ✓
   - Access network discovery ✓
5. Verify VIEWER **CANNOT**:
   - Click shutdown/restart buttons (disabled or hidden) ✓
   - Access "Activity & Audit Log" section ✓
   - See administrator panels ✓

### Step I2: Test OPERATOR Role Permissions

1. Log in as OPERATOR user
2. Verify OPERATOR **CAN**:
   - Perform shutdown/restart operations ✓
   - View workstation status ✓
   - View screen ✓
3. Verify OPERATOR **CANNOT**:
   - Access audit logs ✓
   - Access admin panels ✓

### Step I3: Verify ADMIN Full Access

1. Log in as ADMIN user
2. Verify **ALL** operations accessible:
   - Workstation management ✓
   - Screen viewing ✓
   - Power operations ✓
   - Audit logs visible ✓
   - Admin panels visible ✓

**Test Result: [✓] PASS / [ ] FAIL**

---

## PHASE J: FAILURE SCENARIO TESTS

### Test J1: Wrong Password Rejection

1. Navigate to login: `http://192.168.1.100:8000/login`
2. Enter: Username `admin`, Password `WrongPassword123`
3. Click **Sign In**
4. **Expected**: Error message "Invalid credentials"
5. Session not created

### Test J2: Invalid Agent Token Rejection

1. Stop lab agent
2. Edit `agent.env` on lab PC, change `LAB_AGENT_TOKEN` to incorrect value
3. Restart agent
4. Agent logs show:
   ```
   ERROR: Authentication failed - Invalid enrollment token
   ```
5. Agent does NOT register

### Test J3: Offline Agent Response

1. Dashboard shows workstation as OFFLINE
2. Try to perform power operation → Button disabled or grayed out
3. Try to view screen → Error: "No active screen source"

### Test J4: Duplicate Power Commands

1. Click **Shutdown**
2. Confirm immediately
3. Click **Shutdown** again immediately (before first completes)
4. **Expected**: Second command rejected with `HTTP 409 Conflict`
5. Toast: "A power command is already pending"

### Test J5: Unauthenticated Access

1. Open new incognito/private browser window
2. Navigate to: `http://192.168.1.100:8000/`
3. **Expected**: Redirects to `/login`
4. Cannot access dashboard without valid session

**Test Results Summary:**
- Wrong password: [✓] PASS / [ ] FAIL
- Invalid token: [✓] PASS / [ ] FAIL
- Offline agent: [✓] PASS / [ ] FAIL
- Duplicate commands: [✓] PASS / [ ] FAIL
- Unauthenticated access: [✓] PASS / [ ] FAIL

---

## FINAL VALIDATION CHECKLIST

Mark each section:

- [ ] **Phase A** - Server setup and health check passed
- [ ] **Phase B** - Windows agent installed and running
- [ ] **Phase C** - Dashboard login and workstation visible
- [ ] **Phase D** - Heartbeat and offline detection working
- [ ] **Phase E** - Live screen viewing functional
- [ ] **Phase F** - Network discovery scanning works
- [ ] **Phase G** - Power operations queue correctly (dry-run safe)
- [ ] **Phase H** - Data persists after server restart
- [ ] **Phase I** - RBAC enforced correctly
- [ ] **Phase J** - Failure scenarios handled gracefully

**Overall Result:**
```
All tests passed: [✓] YES / [ ] NO
```

---

## TROUBLESHOOTING QUICK REFERENCE

| Problem | Solution |
|---------|----------|
| Agent won't connect to server | Check server IP is correct; verify firewall allows port 8000; ping server IP from workstation |
| Workstation appears OFFLINE immediately | Check agent token matches server enrollment secret exactly; verify network connectivity |
| Screen viewing shows blank frame | Agent might not have X11/desktop available; check agent logs for screenshot errors |
| Power command fails silently | Check LAB_POWER_DRY_RUN setting on both server and agent matches; verify agent has permissions |
| Dashboard won't load | Check server is running; try clearing browser cache; verify port 8000 is accessible |
| Tests hang during network discovery | Subnet scan might be slow on large networks; normal behavior up to 15 seconds |

---

## Notes for Manual Testing

- **Keep `LAB_POWER_DRY_RUN=true`** during all manual testing to prevent accidental system shutdown
- Test one phase completely before moving to the next
- Record any unexpected behavior or errors for troubleshooting
- If a phase fails, review server/agent logs for detailed error messages
- Network discovery may show more devices than expected (entire subnet is scanned)

---

**Document Version:** 1.0  
**Last Updated:** 2026-09-01  
**Status:** Ready for Windows Manual Testing

# Computer Lab Management - Demonstration Guide
## 5-10 Minute Walkthrough for College Project Presentation

This guide provides a concise demonstration flow suitable for a college project presentation or quick technology showcase. The complete demonstration takes **5-10 minutes** depending on pacing and depth.

---

## Pre-Demonstration Setup (15 minutes before start)

### Prerequisites
1. **Server PC**: Running LabManagement server with valid `.env` configuration
   ```cmd
   python -m server.main
   ```
   Verify: http://localhost:8000/api/health returns `{"status": "running"}`

2. **Workstation PC**: Lab agent running and ONLINE in dashboard
   ```cmd
   .\deploy\windows\start_agent.bat
   ```
   Verify: Workstation appears in dashboard with `🟢 ONLINE` status

3. **Browser**: Open dashboard on server PC
   ```
   http://localhost:8000/
   ```

4. **Credentials Ready**: Username `admin` and its password

---

## DEMO PHASE 1: LOGIN & DASHBOARD OVERVIEW (1 minute)

**Narrative:** "The LabManagement system provides a centralized dashboard for managing multiple lab computers across a network."

### Actions
1. **Screenshot**: Point camera at login page
   - Show URL: `http://192.168.1.100:8000/` (or localhost)
   - Explain: "This is the operator console for the lab"

2. **Enter credentials**:
   - Username: `admin`
   - Password: (configured value)
   - Click **Sign In**

3. **Dashboard loads**:
   - Point to top-right: Shows `👤 admin` with `ADMIN` badge (green)
   - Point to server status: `🟢 Connected`
   - Say: "We're now logged in as an administrator"

---

## DEMO PHASE 2: WORKSTATION INVENTORY & LIVE STATUS (1-2 minutes)

**Narrative:** "The system automatically discovers and registers computers on the laboratory network. Let's view the current inventory."

### Actions
1. **Highlight Summary Cards** (top-right):
   - Total: X computers
   - Online: X (with green status)
   - Offline: X (with gray status)
   - Say: "Real-time status of all lab computers"

2. **Point to Computer Inventory Table**:
   - Column headers: Status | Hostname | IP Address | OS | Last Heartbeat | Actions
   - Click on one workstation row to select it
   - Details panel opens on right side

3. **Highlight Workstation Details**:
   - Hostname (computer name)
   - IP Address (network identity)
   - Operating System (Windows 10, Linux, etc.)
   - Agent ID (unique persistent identifier)
   - Last Heartbeat (timestamp of latest communication)

4. **Say**: "Each computer reports its status every 5 seconds. The system knows which machines are online and ready."

---

## DEMO PHASE 3: LIVE SCREEN VIEWING (2 minutes)

**Narrative:** "Instructors can monitor student lab work in real-time by viewing live desktop screens."

### Actions
1. **In Details Panel**, click **📺 View Live Screen** button
   - Say: "Establishing secure WebSocket connection to workstation..."

2. **Screen modal opens**:
   - Status shows: "Connected (Waiting for frames)"
   - After 1-2 seconds: "● LIVE STREAM" appears with pulsing indicator
   - Desktop screenshot loads in the viewport

3. **On workstation PC** (if visible to audience):
   - Open a notepad or application
   - Type something on the desktop
   - Point: "Watch the screen update in real-time"

4. **Back to Dashboard**:
   - Screenshot updates every half-second
   - Say: "The instructor can monitor activity without visiting each desk"
   - Click **✕** to close screen viewer

---

## DEMO PHASE 4: NETWORK DISCOVERY (1-2 minutes)

**Narrative:** "The system can scan the entire local subnet to identify devices."

### Actions
1. **Scroll down** to **Network Discovery** section
2. **Click "Scan Network"** button
   - Button shows "Scanning subnet..." with spinner
   - Say: "Probing the local network for active devices..."

3. **Wait for scan to complete** (5-15 seconds)
   - Scan finishes
   - List shows discovered devices:
     - IP addresses
     - Hostnames (if available)
     - Status: "Discovered Endpoint"

4. **Explain the difference**:
   - Registered agents in Inventory: "Active LabManagement agents"
   - Discovered devices: "Any active device on the subnet (printers, servers, etc.)"
   - Say: "Network scanning helps identify unregistered or new devices"

---

## DEMO PHASE 5: ROLE-BASED ACCESS CONTROL (1 minute)

**Narrative:** "The system enforces role-based permissions. Different users have different capabilities."

### Actions
1. **Point to ADMIN badge** (top-right)
   - Say: "Admin role has full access to all features"

2. **Click Logout** (top-right menu)
   - Say: "Let me show how different roles have different permissions"

3. **Re-login as admin** (or show on screen):
   - Explain: "Three roles exist in the system:
     - **VIEWER**: Can monitor screens and view status (no control)
     - **OPERATOR**: Can also perform power operations
     - **ADMIN**: Full access including audit logs and user management"

4. **Show in dashboard**:
   - ADMIN users see: "Activity & Audit Log" section
   - Point to power buttons (Shutdown/Restart) - available only to OPERATOR/ADMIN
   - Say: "The system enforces these permissions on the server side"

---

## DEMO PHASE 6: DRY-RUN POWER OPERATIONS (2 minutes)

**Narrative:** "Instructors can perform maintenance tasks like restarting computers - but with a safety mode during testing."

### Actions
1. **Click Workstation Details**:
   - If ONLINE, buttons show: **⏻ Shutdown** | **↻ Restart**
   - Say: "Power control buttons are available for this online workstation"

2. **Click ↻ Restart button**:
   - Confirmation dialog opens
   - Shows: "Confirm Computer Restart"
   - Warning message: "Users currently working will be interrupted..."
   - Workstation details: Hostname, IP address

3. **Explain Safety Mode**:
   - Say: "We're in **DRY-RUN MODE** for testing. No actual restart occurs."
   - Point to `.env` setting: `LAB_POWER_DRY_RUN=true`
   - Explain: "Before production use, this must be set to `false`"

4. **Click "Restart Workstation"** (red button):
   - Toast notification: "Restart command successfully queued..."
   - Say: "The command has been sent"

5. **On workstation console** (if visible):
   - Show agent logs:
     ```
     INFO: Received power command: restart
     INFO: DRY RUN - Would execute: shutdown -r -t 60
     INFO: Command acknowledged
     ```
   - Point: "See? The agent acknowledged the command but did NOT restart (dry-run)"

6. **Back to Dashboard**:
   - Say: "In production, the computer would actually restart"
   - Point to Activity Log entry for this power command

---

## DEMO PHASE 7: AUDIT & SECURITY LOGGING (1 minute)

**Narrative:** "All actions are logged for security and accountability."

### Actions
1. **Scroll down** to **Activity & Audit Log** section
2. **Show recent entries**:
   - Login events: username, timestamp, result
   - Power operations: which computer, which user, action taken
   - Screen viewing sessions: when started/stopped
   - Each entry has: timestamp, action, user, target resource, result

3. **Explain Security Features**:
   - Say: "Passwords and tokens are **never logged**"
   - Explain: "Only user actions and system events are recorded"
   - Say: "This creates an audit trail for compliance and troubleshooting"

---

## DEMO PHASE 8: DATABASE PERSISTENCE (1 minute, Optional)

**Narrative:** "The system stores all data persistently, even after restart."

### Actions (Only if time permits)
1. **On server PC**, stop the server:
   - Press `Ctrl+C`
   - Wait for shutdown message

2. **On dashboard browser**:
   - Page shows connection error (normal)
   - Say: "The server has stopped"

3. **Restart server**:
   ```cmd
   python -m server.main
   ```
   - Wait for startup message

4. **Refresh dashboard** (F5):
   - Dashboard loads normally
   - Same workstation still visible
   - All previous data preserved
   - Say: "Even after restart, all registered computers and audit logs persist"

---

## DEMO PHASE 9: Q&A / DISCUSSION (Remaining time)

**Talking Points:**
- **Architecture**: "Central FastAPI server + Python agents on each workstation"
- **Security**: "Scrypt password hashing, role-based access control, audit logging"
- **Network**: "Works on local subnets (192.168.x.x, 10.x.x.x)"
- **Platforms**: "Agents available for Windows, Linux, and macOS"
- **Use Cases**: 
  - Monitor student lab work
  - Remote troubleshooting
  - Batch power operations for lab closes
  - Track system usage and access patterns

**Potential Questions:**
- **Q: Can it work over the internet?**
  - A: Currently designed for LAN only. Could be extended with VPN or reverse proxy + HTTPS.

- **Q: What if an agent stops responding?**
  - A: Marked OFFLINE after 15 seconds of no heartbeat. Can be restarted locally or via remote reboot (once online).

- **Q: How many workstations can it manage?**
  - A: Designed for 50-200 workstations. Scales with database size and WebSocket handling.

- **Q: Can students see other students' screens?**
  - A: No. Only users with VIEWER+ role can access screens, determined by the admin.

---

## DEMONSTRATION SCRIPT TEMPLATE

**Use this script as a guide:**

---

"Today I'm showing you the **Computer Lab Management System** — a solution for managing multiple lab computers from a single dashboard.

[Show login page] 

This is the secure login. Administrators and instructors use this. Let me log in.

[Login]

Now we're in the dashboard. [Point to summary cards] Here's the real-time status of all lab computers. We have 5 registered, all online.

[Click on one workstation]

These are the details of this workstation — hostname, IP address, operating system, and when it last reported status. 

[Click View Screen]

This opens a live remote screen. The instructor can monitor student work without walking around the lab.

[Show for a few seconds, then close]

We can also scan the network to find devices, perform power operations like restart, and the system logs every action. [Point to audit log]

The entire system is built with security in mind — role-based access control, secure authentication, and comprehensive logging.

Any questions?"

---

## Tips for Smooth Demonstration

1. **Network Connectivity**: Ensure workstation agent stays ONLINE throughout. Check before starting.

2. **Screen Viewing**: Takes 1-2 seconds to load first frame. Don't panic if there's a delay.

3. **Network Scan**: Can take 5-15 seconds depending on subnet size. Use this time to explain the feature.

4. **Browser Refresh**: If dashboard becomes unresponsive, refresh with `F5`.

5. **Keep Dry-Run Mode ON**: Prevent accidental system shutdown during demo.

6. **Have Backup Plan**: If one feature fails, skip it and move to the next.

7. **Close Extra Tabs**: Close unnecessary browser tabs before demo for cleaner screen.

8. **Prepare Talking Points**: Have 2-3 talking points memorized for each phase.

---

## Equipment & Resources Needed

- Projector or screen sharing (if presenting to audience)
- 2 computers (or 1 if showing screenshots)
- Network connectivity between systems
- Working `.env` configuration on server
- Running lab agent on at least one workstation

---

## Demonstration Timing Guide

| Phase | Duration | Notes |
|-------|----------|-------|
| 1. Login & Dashboard | 1 min | Quick overview |
| 2. Workstation Inventory | 1-2 min | Point out features |
| 3. Live Screen Viewing | 2 min | Show real-time capability |
| 4. Network Discovery | 1-2 min | Scan takes time |
| 5. RBAC Explanation | 1 min | Explain permissions |
| 6. Power Operations | 2 min | Show queuing, dry-run |
| 7. Audit Logging | 1 min | Show security |
| 8. Persistence | 1 min | Optional, time-intensive |
| 9. Q&A | 2-3 min | Answer questions |
| **TOTAL** | **~13 min** | Can trim to 5-7 min if needed |

---

**Document Version:** 1.0  
**Last Updated:** 2026-09-01  
**Status:** Ready for Presentation

# Firewall Configuration Guide
## LabManagement Server & Agent Port Access

This guide explains how to configure firewall rules on Windows and Linux to allow LabManagement traffic while maintaining security.

---

## Overview

**Default LabManagement Ports:**
- **Server Port**: TCP 8000 (dashboard, API, WebSocket)
- **Agent Communication**: Initiates outbound to server port 8000

**Network Design:**
- Server listens on all network interfaces (`0.0.0.0:8000`)
- Agents connect outbound to server LAN IP and port 8000
- No inbound connections from agents required on Windows (outbound-only)

---

## WINDOWS FIREWALL CONFIGURATION

### For Server PC (Running FastAPI Server)

#### Option 1: Windows Defender Firewall GUI (Recommended for Most Users)

1. **Open Windows Defender Firewall with Advanced Security:**
   - Press `Windows + R`
   - Type: `wf.msc`
   - Press Enter

2. **Create Inbound Rule for Port 8000:**
   - Left panel: Click **Inbound Rules**
   - Right panel: Click **New Rule...**
   - Rule Type: Select **Port**
   - Protocol: Select **TCP**
   - Port: **Specific ports** → enter `8000`
   - Action: Select **Allow**
   - Profile: Check **Private** (Lab network), leave **Public** unchecked
   - Name: `LabManagement Server`
   - Finish

3. **Verify Rule Created:**
   - In Inbound Rules list, find `LabManagement Server`
   - Status should show: `Enabled`

#### Option 2: PowerShell Command (Faster for Automation)

Run as Administrator:

```powershell
# Allow inbound TCP on port 8000 for private networks only
New-NetFirewallRule -DisplayName "LabManagement Server" `
  -Direction Inbound `
  -Action Allow `
  -Protocol TCP `
  -LocalPort 8000 `
  -Profile Private `
  -ErrorAction SilentlyContinue

Write-Host "Firewall rule added for LabManagement Server port 8000"
```

### For Workstation PC (Running Lab Agent)

**No special inbound firewall rules needed.** The agent initiates outbound connections, which Windows allows by default.

#### Verify Outbound Connectivity (Optional)

From workstation command prompt:
```cmd
ping <SERVER_LAN_IP>
telnet <SERVER_LAN_IP> 8000
```

If `telnet` is not available, install it:
```powershell
dism /Online /Add-Capability /CapabilityName:TelnetClient~~~~0.0.1.0
```

---

## LINUX FIREWALL CONFIGURATION

### For Server PC (Running FastAPI Server)

#### Using UFW (Ubuntu/Debian) - Simplest

1. **Check if UFW is installed:**
   ```bash
   sudo ufw status
   ```

2. **Enable UFW if not already enabled:**
   ```bash
   sudo ufw enable
   ```

3. **Allow SSH first (to avoid lockout):**
   ```bash
   sudo ufw allow 22/tcp
   ```

4. **Allow LabManagement port from private subnet:**
   ```bash
   # Allow from specific subnet (example: 192.168.1.0/24)
   sudo ufw allow from 192.168.1.0/24 to any port 8000

   # Or allow from any internal source (less restrictive)
   sudo ufw allow 8000/tcp
   ```

5. **Verify rules:**
   ```bash
   sudo ufw status verbose
   ```

   Expected output:
   ```
   Status: active

   To                         Action      From
   --                         ------      ----
   22/tcp                     ALLOW       Anywhere
   8000/tcp                   ALLOW       192.168.1.0/24
   ```

#### Using iptables (Advanced / RHEL/CentOS)

```bash
# Check current rules
sudo iptables -L -n

# Allow SSH
sudo iptables -A INPUT -p tcp --dport 22 -j ACCEPT

# Allow LabManagement from private subnet
sudo iptables -A INPUT -p tcp --dport 8000 -s 192.168.1.0/24 -j ACCEPT

# Drop all other inbound by default
sudo iptables -P INPUT DROP

# Save rules (Debian/Ubuntu):
sudo iptables-save | sudo tee /etc/iptables/rules.v4
```

### For Workstation PC (Running Lab Agent)

**No inbound rules needed.** The agent only requires outbound access to server port 8000.

#### Verify Outbound Connectivity:

```bash
# Test connectivity to server
ping <SERVER_LAN_IP>
curl http://<SERVER_LAN_IP>:8000/api/health
```

Should return:
```json
{"status": "running"}
```

---

## macOS FIREWALL CONFIGURATION

### For Server PC

#### Using System Preferences (GUI)

1. **Open System Preferences** → **Security & Privacy** → **Firewall Options**
2. **Firewall**: Ensure it's enabled
3. By default, macOS allows inbound connections from localhost and same subnet
4. To specifically allow port 8000:
   - Click **Firewall Options**
   - Click the lock icon to make changes (authenticate)
   - **Add** the Python process or use Terminal method below

#### Using Terminal (Recommended)

```bash
# Check firewall status
sudo /usr/libexec/ApplicationFirewall/socketfilterfw -getglobalstate

# Allow inbound on port 8000
sudo /usr/libexec/ApplicationFirewall/socketfilterfw -setallowsigned on
sudo /usr/libexec/ApplicationFirewall/socketfilterfw -setallowsignedapp on

# Alternatively, add a firewall rule via pf (packet filter)
echo "pass in proto tcp from any to any port 8000" | sudo tee /etc/pf.anchors/labmanagement
sudo pfctl -f /etc/pf.conf
```

### For Workstation PC

No additional configuration needed. Agent only requires outbound connectivity.

---

## SECURITY BEST PRACTICES

### ✅ DO

- **Restrict to Private Subnet**: Use `192.168.1.0/24`, `10.0.0.0/8` ranges only
- **Deny Public Internet**: Never expose port 8000 to the public internet
- **Use HTTPS in Production**: Place server behind reverse proxy (Nginx) with SSL/TLS
- **Monitor Firewall Logs**: Review inbound connection attempts regularly
- **Principle of Least Privilege**: Only allow necessary ports from necessary sources

### ❌ DON'T

- **Don't expose 0.0.0.0:8000 to the internet** — anyone could access your lab
- **Don't disable firewall entirely** — use rules instead
- **Don't allow public internet source ranges** (0.0.0.0/0 for inbound)
- **Don't put real secrets in examples** — use `.env.example` only

---

## Firewall Rule Verification

### Test from Workstation

```bash
# Linux/macOS/Windows WSL
curl http://<SERVER_LAN_IP>:8000/api/health

# Expected response
{"status": "running"}
```

### Test from Server

```bash
# Verify port is listening
netstat -tuln | grep 8000

# On Windows:
netstat -ano | findstr :8000

# On Linux/macOS:
lsof -i :8000
```

### Troubleshooting Firewall Issues

| Symptom | Diagnosis | Solution |
|---------|-----------|----------|
| Agent can't connect to server | Port blocked or service not running | Check firewall rule exists; verify `python -m server.main` is running |
| "Connection refused" error | Server not listening on port | Restart server; check port isn't in use by other app |
| Can ping server but can't reach port 8000 | Firewall blocking TCP specifically | Ensure TCP rule (not just ICMP) is added for port 8000 |
| Dashboard loads locally but not from LAN | Binding to localhost instead of 0.0.0.0 | Check `LAB_SERVER_HOST=0.0.0.0` in `.env` |

---

## Production / Campus Deployment

For deployment beyond a single lab network:

### HTTPS/TLS Setup (Required for Security)

1. **Install Nginx or Caddy** as reverse proxy in front of FastAPI
2. **Obtain SSL certificate** (Let's Encrypt free or institutional CA)
3. **Configure reverse proxy** to forward HTTPS → HTTP (internal FastAPI)
4. **Set `LAB_SECURE_COOKIES=true`** in `.env`
5. **Firewall rule**: Allow TCP 443 (HTTPS) instead of 8000

### Example Nginx Configuration

```nginx
server {
    listen 443 ssl http2;
    server_name lab.example.edu;

    ssl_certificate /etc/ssl/certs/lab.crt;
    ssl_certificate_key /etc/ssl/private/lab.key;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }

    # Redirect HTTP to HTTPS
    if ($scheme != "https") {
        return 301 https://$server_name$request_uri;
    }
}
```

Then firewall rule becomes:
```bash
sudo ufw allow 443/tcp
```

---

## Quick Reference Commands

### Windows (PowerShell)

```powershell
# Add rule
New-NetFirewallRule -DisplayName "LabMgmt" -Direction Inbound -Action Allow -Protocol TCP -LocalPort 8000 -Profile Private

# Remove rule
Remove-NetFirewallRule -DisplayName "LabMgmt"

# List all rules
Get-NetFirewallRule -DisplayName "LabMgmt"
```

### Linux (UFW)

```bash
# Add rule
sudo ufw allow from 192.168.1.0/24 to any port 8000

# Remove rule
sudo ufw delete allow from 192.168.1.0/24 to any port 8000

# View rules
sudo ufw show added
```

### macOS (pf)

```bash
# View packet filter rules
sudo pfctl -s rules

# Load rules from file
sudo pfctl -f /etc/pf.conf

# Flush all rules
sudo pfctl -F all
```

---

## Verification Checklist

Before considering the firewall properly configured:

- [ ] Server port 8000 is open to private subnet
- [ ] Agent can reach server: `curl http://<SERVER_IP>:8000/api/health` returns 200
- [ ] Dashboard accessible from workstation browser: `http://<SERVER_IP>:8000/`
- [ ] Agent logs show "Connected to server" message
- [ ] Workstation appears ONLINE in dashboard within 5 seconds
- [ ] No firewall errors in system logs
- [ ] Public internet CANNOT reach port 8000 (test with external IP if possible)

---

## Support & Troubleshooting

If firewall is correctly configured but connectivity still fails:

1. **Check server is actually running:**
   ```bash
   python -m server.main
   ```

2. **Verify server is listening:**
   ```bash
   # Windows: netstat -ano | findstr :8000
   # Linux: sudo netstat -tlnp | grep 8000
   # macOS: lsof -i :8000
   ```

3. **Check for other services on port 8000:**
   ```bash
   # Try different port in `.env`
   LAB_SERVER_PORT=8001
   ```

4. **Test basic connectivity:**
   ```bash
   # From workstation, test if server responds at all
   ping <SERVER_IP>
   ```

5. **Review server/agent logs** for authentication or connection errors

---

**Document Version:** 1.0  
**Last Updated:** 2026-09-01  
**Status:** Ready for Deployment

# Security Documentation
## LabManagement Platform Security Features & Best Practices

---

## Table of Contents
1. [Security Features](#security-features)
2. [Authentication & Authorization](#authentication--authorization)
3. [Data Protection](#data-protection)
4. [Network Security](#network-security)
5. [Deployment Security](#deployment-security)
6. [Security Audit Findings](#security-audit-findings)
7. [Incident Response](#incident-response)
8. [Security Checklist](#security-checklist)

---

## Security Features

### Cryptographic Security

#### Password Storage
- **Algorithm**: scrypt with strong parameters (n=2^14, r=8, p=1)
- **Salt**: Unique per password, generated with `secrets` module
- **Hash verification**: Constant-time comparison prevents timing attacks
- **Rainbow table resistant**: Unique salt + high iteration count

#### Session Management
- **Session tokens**: Generated with `secrets.token_hex(16)`
- **Storage**: HttpOnly, Secure, SameSite=Lax cookies
- **Expiration**: Configurable via `LAB_SESSION_MAX_AGE` (default 28800 seconds = 8 hours)
- **Revocation**: Immediate on logout via database deletion

#### Enrollment Secret
- **Length**: Minimum 24 characters (enforced at startup)
- **Validation**: Constant-time HMAC comparison prevents timing attacks
- **Per-agent**: Future enhancement planned for per-agent tokens

### Input Validation

#### API Endpoints
All JSON request bodies validated with Pydantic:
```python
class AgentRegistration(BaseModel):
    agent_id: str = Field(min_length=36, max_length=36)  # UUID format
    hostname: str = Field(min_length=1, max_length=255)
    ip_address: str = Field(min_length=3, max_length=45)  # IPv4/IPv6
    operating_system: str = Field(min_length=1, max_length=255)
```

- **Custom validators**: UUID and IP address validation
- **Type checking**: FastAPI automatic type enforcement
- **Length limits**: Prevent buffer overflow attacks
- **Injection prevention**: No raw SQL queries used

### Database Security

#### SQL Injection Prevention
All SQL queries use parameterized statements:
```python
# ✓ SAFE - parameterized
db.execute("SELECT * FROM users WHERE username = ?", (username,))

# ✗ UNSAFE - would be vulnerable
db.execute(f"SELECT * FROM users WHERE username = '{username}'")
```

Database functions never accept raw SQL from user input.

#### Credential Storage
- User passwords: scrypt-hashed (never stored plaintext)
- Enrollment token: environment variable only (never stored in database)
- Session IDs: stored in database but cryptographically random
- Database file: Created with mode `0o600` (owner read/write only)

### WebSocket Security

#### Frame Validation
- Frame data: Base64 validation before processing
- Frame content: JPEG magic bytes validated (FFD8FF)
- Frame size: Limited to 5MB per frame
- Message type validation: Only "frame" and "ping" types accepted

#### Connection Authentication
- Screen sources (agents): Validated with X-Agent-Token header
- Screen viewers (browsers): Validated with user session cookie
- Handshake timeout: 5 seconds to prevent resource exhaustion
- Idle timeout: 60 seconds for sources, 300 seconds for viewers

### HTTP Security Headers

Added via `SecurityHeadersMiddleware`:
```
X-Frame-Options: DENY                    # Clickjacking protection
X-Content-Type-Options: nosniff          # MIME sniffing prevention
X-XSS-Protection: 1; mode=block          # Browser XSS filters
Referrer-Policy: strict-origin-when-cross-origin  # Information disclosure prevention
Permissions-Policy: geolocation=(), microphone=(), camera=()  # Feature isolation
Strict-Transport-Security: max-age=31536000  # HTTPS enforcement (when enabled)
```

### CORS Protection

- **SessionMiddleware** with HttpOnly cookies prevents CSRF
- **SameSite=Lax** prevents most cross-site attack vectors
- Reverse proxy (nginx/caddy) can add additional CORS headers

---

## Authentication & Authorization

### Role-Based Access Control (RBAC)

Three user roles with enforced permissions:

#### VIEWER
**Permissions:**
- View workstation inventory ✓
- View workstation details ✓
- View live screen streams ✓
- Perform network discovery scans ✓

**Restrictions:**
- ✗ Cannot perform power operations
- ✗ Cannot access audit logs
- ✗ Cannot access admin APIs

**Enforcement:** `require_viewer()` dependency in FastAPI

#### OPERATOR
**Permissions:**
- All VIEWER permissions ✓
- Perform shutdown/restart operations ✓

**Restrictions:**
- ✗ Cannot access audit logs
- ✗ Cannot access admin panels
- ✗ Cannot modify user roles

#### ADMIN
**Permissions:**
- All OPERATOR permissions ✓
- View audit logs and activity ✓
- Access admin status endpoints ✓
- Access persistent agent inventory ✓

### Authentication Flow

```
Browser                    Server
  |                          |
  |--[POST /api/auth/login]-->|
  |   (username, password)     |
  |                            |
  |<--[Session Cookie]---------|
  |    (HttpOnly, SameSite)    |
  |                            |
  |--[GET /api/agents]-------->|
  |   (Cookie auto-included)   |
  |                            |
  |<--[Agents List]-----------|
```

### Session Validation

Every protected API endpoint validates:
1. Session cookie present
2. Session ID exists in database
3. Session not expired (current_time < creation_time + max_age)
4. User role sufficient for endpoint (require_admin, require_operator, etc.)

If any check fails: `HTTP 401 Unauthorized` or `HTTP 403 Forbidden`

### Power Command Pipeline

1. User requests shutdown via dashboard
2. API checks: User role is OPERATOR or ADMIN
3. Check: No pending command for this agent
4. Queue command in database with HMAC signature
5. Agent polls `/power-command` endpoint
6. Agent validates HMAC signature
7. Agent executes command (or dry-run)
8. Agent sends acknowledgement with command result
9. Server validates acknowledgement HMAC
10. Audit log records: username, agent, action, result

---

## Data Protection

### In Transit

#### Unencrypted (Lab Network Only)
- Default deployment: HTTP (not HTTPS)
- **Important**: Only suitable for trusted lab networks
- No encryption over the wire

#### Encrypted (Production/Campus)
For campus-wide or production deployment:
1. Place FastAPI server behind reverse proxy (Nginx/Caddy)
2. Obtain TLS certificate (Let's Encrypt free, or institutional CA)
3. Configure reverse proxy with SSL/TLS
4. Set `LAB_SECURE_COOKIES=true` in `.env`
5. Update agent `LAB_SERVER_URL` to `https://...`

#### VPN Alternative
- Deploy server on VPN-isolated subnet
- Workstations connect via VPN to access lab server
- VPN provides encryption and authentication

### At Rest

#### Database Encryption
SQLite database file (`labmanagement.sqlite3`):
- **File permissions**: `0o600` (owner read/write only)
- **Encryption**: Not enabled by default (lab network only)
- **For sensitive data**: Use SQLCipher extension for encrypted SQLite

#### Configuration Files
- **`.env`**: Contains secrets, **MUST NOT be committed to git**
- **`agent.env`**: Contains enrollment token, **restricted to mode 0o600**
- **`.gitignore`**: Prevents accidental commits of `.env` files

#### Secrets Management (Production)
For production/enterprise deployment:
- Use HashiCorp Vault for centralized secret management
- Use AWS Secrets Manager or Azure Key Vault for cloud deployment
- Implement secret rotation policies
- Audit all secret access

---

## Network Security

### Port Isolation

**Server (TCP 8000):**
- Listens on all interfaces (`0.0.0.0:8000`)
- Firewall should restrict to private subnet only
- No direct internet exposure

**Agent (Outbound Only):**
- Initiates outbound connections to server port 8000
- No inbound listening required
- Connectionless protocol (HTTP polling + WebSocket)

### LAN-Only Deployment

Current design assumes:
- **Network**: Private lab local area network (192.168.x.x, 10.x.x.x)
- **Firewall**: Hardware firewall isolates lab from public internet
- **Access**: Only lab machines and administrator terminals

**Security Assumption**: All devices on lab LAN are trusted

### Firewall Configuration

See [FIREWALL_SETUP.md](FIREWALL_SETUP.md) for detailed firewall rules

**Quick Rules:**
```bash
# Linux (UFW)
sudo ufw allow from 192.168.1.0/24 to any port 8000

# Windows (PowerShell)
New-NetFirewallRule -DisplayName "LabMgmt" -Direction Inbound `
  -Action Allow -Protocol TCP -LocalPort 8000 -Profile Private
```

### Network Discovery Safety

Network discovery (`/api/discovery/scan`):
- Performs bounded ICMP ping sweep of local `/24` subnet
- Timeout: 10 seconds per host (max ~2550 hosts in 255 seconds)
- No port scanning, no service enumeration
- Results are informational only

---

## Deployment Security

### Server Deployment

#### Minimum Security Requirements
1. [ ] Create `.env` with random secrets (32+ character APP_SECRET, 24+ character ENROLLMENT_SECRET)
2. [ ] `.env` file is **NOT** committed to git
3. [ ] `.env` file permissions: `0o600` (owner only)
4. [ ] Run server as non-root user
5. [ ] Firewall restricts port 8000 to private subnet
6. [ ] Database file created with `0o600` permissions

#### Recommended for Production
1. [ ] HTTPS/TLS enabled via reverse proxy
2. [ ] Set `LAB_SECURE_COOKIES=true` in `.env`
3. [ ] Database backup strategy implemented
4. [ ] Log export to centralized syslog server
5. [ ] Rate limiting on `/api/auth/login` endpoint
6. [ ] Regular security updates for Python and dependencies

### Agent Deployment

#### Windows Agent
- `agent.env` file: `LAB_AGENT_TOKEN` must be kept confidential
- Setup script: `icacls` restricts `agent.env` to user ownership only
- Running as: Same user context (no elevation needed for monitoring)
- Screen capture: Requires display access (fails gracefully if no display)

#### Linux Agent
- `agent.env` file: `chmod 600` by setup script
- systemd service: Runs as dedicated `labuser` account (non-root)
- Permissions: `sudo` entry for `shutdown`/`reboot` if power operations enabled
- Screen capture: Requires X11 or Wayland session access

#### macOS Agent
- `agent.env`: Stored in project directory with restricted permissions
- launchd plist: Runs in user context (not as daemon)
- Keychain: Could be integrated for token storage (future enhancement)

---

## Security Audit Findings

### Addressed Issues (Fixed)

✓ **Removed hardcoded IP from macOS plist** - Changed from `192.168.1.100` to placeholder `REPLACE_WITH_SERVER_IP`

✓ **XSS Vulnerability Mitigated** - Added base64 and JPEG magic byte validation in WebSocket frame handler

✓ **Missing .gitignore** - Created comprehensive `.gitignore` to prevent secret commits

✓ **Missing Security Headers** - Added `SecurityHeadersMiddleware` to enforce HTTP security headers

✓ **WebSocket Timeouts** - Added 60-second idle timeout for source, 300-second for viewers

✓ **File Permission Hardening** - Setup scripts now set `agent.env` permissions to `0o600` (Linux) and restricted ownership (Windows)

### Known Limitations

⚠ **Single Shared Enrollment Secret**
- All agents share the same `LAB_AGENT_ENROLLMENT_SECRET`
- No per-agent token revocation capability
- Future enhancement: Implement per-agent token generation and storage

⚠ **No Rate Limiting on Login**
- Login endpoint has no rate limiting
- Brute-force attacks theoretically possible (but mitigated by strong password)
- Future enhancement: Implement rate limiting with `slowapi` or similar

⚠ **No CSRF Tokens**
- Protected by SameSite cookies for same-origin POST requests
- Lacks explicit CSRF token mechanism
- Low risk for lab environment (trusted operators)

⚠ **Database Not Encrypted**
- SQLite database not encrypted at rest
- Suitable for lab networks (not production enterprise)
- Enhancement: Use SQLCipher for encrypted SQLite

⚠ **Session Not Invalidated on Role Change**
- If user role modified in database, current session remains valid until expiry
- Enhancement: Add version tracking for user roles

### Deferred Issues (Out of Scope for This Release)

- [ ] Per-agent enrollment tokens (instead of single shared secret)
- [ ] Rate limiting on authentication endpoints
- [ ] Explicit CSRF token mechanism (beyond SameSite protection)
- [ ] Database encryption at rest
- [ ] Secrets rotation mechanism
- [ ] External secrets manager integration (Vault, AWS Secrets Manager)
- [ ] TLS/HTTPS configuration examples
- [ ] Penetration testing by external security team

---

## Incident Response

### Suspected Compromise

If the system is suspected to be compromised:

#### Immediate Actions (Within 1 hour)
1. [ ] Disable all user accounts except administrator
2. [ ] Stop the central server process
3. [ ] Stop all lab agent processes
4. [ ] Disable network access to affected machines (if possible)
5. [ ] Contact security team / IT administration
6. [ ] Preserve logs and database for forensic analysis

#### Forensic Analysis
1. [ ] Export audit logs: `SELECT * FROM audit_log ORDER BY timestamp DESC;`
2. [ ] Check for unauthorized power operations
3. [ ] Verify enrollment secret was not changed
4. [ ] Review database for unexpected user accounts
5. [ ] Check for modifications to source code files
6. [ ] Analyze WebSocket frame submissions for anomalies

#### Recovery Steps
1. [ ] Restore database from known-clean backup (if available)
2. [ ] Regenerate all secrets (APP_SECRET, ENROLLMENT_SECRET)
3. [ ] Update `.env` with new secrets on server
4. [ ] Update `agent.env` with new enrollment secret on all agents
5. [ ] Restart server and agents
6. [ ] Re-register all workstation agents
7. [ ] Verify all systems reconnect successfully

### Compromised Enrollment Secret

If `LAB_AGENT_ENROLLMENT_SECRET` is leaked:

1. [ ] Stop all lab agents
2. [ ] Rotate the secret in `.env`: `LAB_AGENT_ENROLLMENT_SECRET=<NEW_SECRET>`
3. [ ] Restart server
4. [ ] Update `agent.env` on all workstations with new secret
5. [ ] Restart all agents
6. [ ] Agents will re-register with new secret
7. [ ] Verify all agents reconnect as ONLINE

### Compromised Database File

If database file (`labmanagement.sqlite3`) is stolen:

1. [ ] Passwords are scrypt-hashed (attacker cannot recover plaintext)
2. [ ] Session IDs are random, but server should be rotated
3. [ ] Enrollment secret is **NOT** in database (safe)
4. [ ] Delete database file: `rm labmanagement.sqlite3`
5. [ ] Restart server (creates new empty database)
6. [ ] All users and agents re-register
7. [ ] Audit logs are lost (should implement external logging)

---

## Security Checklist

### Before Initial Deployment

- [ ] Review all `.env.example` placeholders are replaced with strong values
- [ ] Confirm `.env` is in `.gitignore` and not committed to git
- [ ] Verify Python version 3.12+ installed
- [ ] Confirm all dependencies installed from `requirements.txt`
- [ ] Run automated tests: `python -m unittest discover -s tests -v`
- [ ] Verify all 11 tests pass
- [ ] Test server startup: `python -m server.main`
- [ ] Test dashboard access: http://localhost:8000/
- [ ] Verify initial admin login works

### Before Production Deployment

- [ ] Configure firewall rules (see FIREWALL_SETUP.md)
- [ ] Enable HTTPS/TLS via reverse proxy
- [ ] Set `LAB_SECURE_COOKIES=true`
- [ ] Set `LAB_POWER_DRY_RUN=false` ONLY after testing
- [ ] Implement database backup strategy
- [ ] Set up log export to centralized server
- [ ] Configure rate limiting on login endpoint
- [ ] Test failover/disaster recovery procedures
- [ ] Document incident response procedures
- [ ] Brief staff on access controls and security policies

### Regular Maintenance

- [ ] Monthly: Review audit logs for suspicious activity
- [ ] Quarterly: Update Python and dependencies for security patches
- [ ] Quarterly: Rotate app and enrollment secrets
- [ ] Quarterly: Test database backup and restore procedures
- [ ] Annually: Conduct security review with team
- [ ] Annually: Consider external penetration testing

---

## Security Contact & Support

For security vulnerabilities or questions:
1. Do NOT publicly disclose security issues
2. Contact the development team with detailed information
3. Allow reasonable time for patch development (30-90 days)
4. Coordinate disclosure timeline

---

**Document Version:** 1.0  
**Last Updated:** 2026-09-01  
**Status:** Ready for Deployment

# Windows Manager — One-Click Startup

Use this guide on the instructor or manager PC that runs the LabManagement server and dashboard. The launcher uses the repository's existing FastAPI server, authentication, RBAC, and `.env` configuration; it does not create a second server architecture.

## Manager PC setup

Install Python 3.12 or newer from [python.org](https://www.python.org/downloads/windows/) and select **Add Python to PATH** during installation. Then clone the private repository using an account that has access to it:

```powershell
git clone https://github.com/pujariakash221-eng/LabManagement.git
cd LabManagement
```

On the first run, double-click `START_MANAGER.bat` in Windows Explorer. It can also be started from PowerShell or Command Prompt:

```powershell
.\START_MANAGER.bat
```

The launcher detects Python, creates `.venv` when needed, installs dependencies only when they are missing or `requirements.txt` has changed, creates a secure `.env` from `.env.example` when absent, starts the backend, waits for `/api/health`, and opens the normal dashboard login page.

When a new `.env` is generated, the application secret, enrollment secret, and initial administrator password are generated securely and are never printed. Retrieve the initial administrator password from the protected `.env` file when you need to sign in. Keep that file private and do not commit it.

## Subsequent startup

Double-click `START_MANAGER.bat` again. Existing `.venv` and `.env` files are preserved. If a healthy LabManagement server is already listening on the configured port, the launcher reuses it instead of starting another backend.

By default the server configuration is:

```ini
LAB_SERVER_HOST=0.0.0.0
LAB_SERVER_PORT=8000
```

The launcher prints both the local dashboard address (`http://127.0.0.1:8000/`) and the active manager LAN address (for example, `http://192.168.1.100:8000/`). Use the LAN address from other computers; `127.0.0.1` works only on the manager PC.

## Connecting lab PCs

Install the existing agent on each workstation as described in [INSTALL_AGENT.md](INSTALL_AGENT.md). When prompted for its central server URL, enter the launcher’s **LAN Dashboard** address. When prompted for the enrollment secret, use the value of `LAB_AGENT_ENROLLMENT_SECRET` from the manager PC's `.env` file. Do not send that secret through insecure channels or place it in a command line.

## Firewall setup

If Windows Firewall blocks computers on the lab network, run the included helper in an elevated PowerShell window:

```powershell
.\deploy\windows\setup_manager_firewall.ps1
```

It creates the explicit `LabManagement Manager TCP 8000` inbound rule for TCP port 8000 on the **Private** profile only. It does not disable the firewall or change unrelated rules. Ensure the manager’s network is classified as Private only when that is appropriate for the trusted lab LAN.

## Troubleshooting

- **Python not found or too old:** Install Python 3.12+ and ensure it is on PATH, then rerun the launcher.
- **Port conflict:** If port 8000 answers `/api/health`, the launcher reuses the running LabManagement server. Otherwise it reports the listening process and does not terminate it. Stop or reconfigure that unrelated application yourself.
- **Health check failed:** The launcher prints the recent backend output from `.lab_management\manager-server.out.log` and `.lab_management\manager-server.err.log`. Check those files and `.env`; no secrets are printed by the launcher.
- **LAN computers cannot connect:** Confirm the displayed LAN IP is correct, the manager is connected to the lab network, `LAB_SERVER_HOST=0.0.0.0`, and the Private-profile firewall rule is installed if needed. Test `http://<MANAGER-LAN-IP>:8000/api/health` from a lab PC.
- **No LAN IP displayed:** Connect or enable the correct Ethernet/Wi-Fi adapter and run the launcher again.

## Finding the manager IP

The launcher prints the preferred active IPv4 address. You can also run `ipconfig` and use the IPv4 Address for the Ethernet or Wi-Fi adapter serving the laboratory network. Do not give agents a loopback (`127.0.0.1`) or automatic private (`169.254.x.x`) address.

## Stopping the backend

The backend is intentionally independent of the launcher, so closing the launcher does not stop the server. To stop a server you started, identify its listening process in an elevated PowerShell window and stop that specific process:

```powershell
Get-NetTCPConnection -State Listen -LocalPort 8000 | Select-Object LocalAddress, OwningProcess
Stop-Process -Id <OwningProcess>
```

Only stop a process after confirming it is the LabManagement backend. If the manager uses another configured port, replace `8000` in the command.

## Changing the server port

The existing project supports `LAB_SERVER_PORT` in `.env`. The default is `8000`; changing it requires restarting the backend and using the new port in every agent’s server URL. The provided firewall helper is intentionally for the default TCP port 8000, so create an equivalent Private-profile firewall rule for another chosen port. Keep `LAB_SERVER_HOST=0.0.0.0` for LAN access.

## Security notes

- `.env` is ignored by Git and contains secrets. Never commit, publish, or paste it.
- Keep `LAB_POWER_DRY_RUN=true` until power-control authorization and testing are complete.
- For production HTTPS deployments, keep the project’s existing `LAB_SECURE_COOKIES=true` guidance and use a suitable TLS reverse proxy.
- The dashboard remains protected by the existing login and role-based access controls.

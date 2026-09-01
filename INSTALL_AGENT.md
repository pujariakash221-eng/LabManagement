# Windows agent installation

Use this procedure to install a LabManagement agent from the private GitHub repository on a Windows workstation. Run it in an **elevated PowerShell window**; the installer registers a LocalSystem startup task.

## One-command installation

Install [Git for Windows](https://git-scm.com/download/win) first. It must be able to authenticate to GitHub (Git Credential Manager is included with current Git for Windows). From any PowerShell directory, run this single command:

```powershell
git clone https://github.com/pujariakash221-eng/LabManagement.git "$env:ProgramData\LabManagement"; & "$env:ProgramData\LabManagement\install-agent.ps1"
```

The repository is private. When Git Credential Manager opens, sign in to a GitHub account that has access to `pujariakash221-eng/LabManagement`. If Git prompts for a token, use a fine-grained personal access token limited to this repository with **Contents: Read** permission. Never put a token in the command line, script, source code, or `agent.env`.

The installer detects Git, uses an existing LabManagement clone when one is already present, and otherwise uses authenticated GitHub CLI or Git Credential Manager cloning. It never uses an unauthenticated `raw.githubusercontent.com` download.

During installation it asks for:

1. The central server URL, for example `http://192.168.1.100:8000`.
2. The agent enrollment secret. This uses PowerShell's secure prompt and is not echoed.

It then creates or reuses `.venv`, installs `requirements.txt`, writes the protected `agent.env`, registers the computer through the existing agent code, creates/replaces the single `LabManagement Agent` scheduled task, starts it, and verifies registration with the server.

`LAB_POWER_DRY_RUN=true` is set on first installation. On later runs the current dry-run setting is preserved; it is never silently changed to `false`.

## Existing clone or one-click launcher

If the repository is already cloned, run this from any directory (the script resolves its own installation directory):

```powershell
& "C:\ProgramData\LabManagement\install-agent.ps1"
```

Or double-click `INSTALL_AGENT.bat` in the cloned repository. It requests the required UAC elevation, then starts the same protected installer. The batch file is only a launcher; it does not contain configuration values or secrets.

## Re-running and verification

Re-running the command is safe. The installer reuses the existing virtual environment and machine identity, reuses settings if you submit an empty prompt where an existing value is shown, and updates the same `LabManagement Agent` task in place instead of creating another task.

After success, verify the task if needed:

```powershell
Get-ScheduledTask -TaskName "LabManagement Agent" -TaskPath "\" | Select-Object TaskName, State
```

The server dashboard should show the workstation as online shortly after the installer completes. To move a trusted production lab out of safe mode, intentionally change `LAB_POWER_DRY_RUN=false` in its protected `agent.env` and restart the scheduled task; do not make that change until power-control authorization and testing are complete.

## Private-repository raw links

Do not use an unauthenticated `https://raw.githubusercontent.com/...` command as an installation mechanism for this private repository. The supported one-command procedure above authenticates GitHub before downloading repository content.

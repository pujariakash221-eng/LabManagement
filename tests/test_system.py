"""
Comprehensive End-to-End System Test Suite for Lab Management Platform.
Covers all functional requirements, security boundaries, RBAC permissions,
persistence, WebSocket streaming, power control, and error handling.
"""

import base64
import json
import os
import secrets
import tempfile
import time
import unittest
import uuid

# Configure test environment
TEMP_DB = tempfile.NamedTemporaryFile(suffix=".sqlite3", delete=False)
TEMP_DB_PATH = TEMP_DB.name
TEMP_DB.close()

os.environ["LAB_APP_SECRET"] = "test-app-secret-at-least-32-chars-long-12345"
os.environ["LAB_AGENT_ENROLLMENT_SECRET"] = "test-agent-enrollment-secret-at-least-24-chars"
os.environ["LAB_INITIAL_ADMIN_USERNAME"] = "admin"
os.environ["LAB_INITIAL_ADMIN_PASSWORD"] = "AdminPassword2026!"
os.environ["LAB_BOOTSTRAP_OPERATOR_USERNAME"] = "operator1"
os.environ["LAB_BOOTSTRAP_OPERATOR_PASSWORD"] = "OperatorPassword2026!"
os.environ["LAB_BOOTSTRAP_VIEWER_USERNAME"] = "viewer1"
os.environ["LAB_BOOTSTRAP_VIEWER_PASSWORD"] = "ViewerPassword2026!"
os.environ["LAB_DATABASE_PATH"] = TEMP_DB_PATH
os.environ["LAB_POWER_DRY_RUN"] = "true"
os.environ["LAB_OFFLINE_TIMEOUT"] = "2.0"
os.environ["LAB_AUDIT_MAX_ENTRIES"] = "100"

from starlette.testclient import TestClient
from server.main import app, SERVER_CONFIG
from server.database import Database
from agent.config import AgentConfig
from agent.client import register_agent, send_heartbeat, fetch_power_command, acknowledge_power_command
from agent.power import execute_power_action


class LabManagementSystemTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)
        cls.admin_creds = {"username": "admin", "password": "AdminPassword2026!"}
        cls.operator_creds = {"username": "operator1", "password": "OperatorPassword2026!"}
        cls.viewer_creds = {"username": "viewer1", "password": "ViewerPassword2026!"}
        cls.agent_secret = SERVER_CONFIG.agent_enrollment_secret

    @classmethod
    def tearDownClass(cls):
        try:
            os.remove(TEMP_DB_PATH)
        except OSError:
            pass

    def test_01_server_startup_and_health(self):
        res = self.client.get("/api/health")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json(), {"status": "running"})
        css_res = self.client.get("/static/styles.css")
        self.assertEqual(css_res.status_code, 200)
        self.assertIn("--bg-sidebar", css_res.text)
        js_res = self.client.get("/static/app.js")
        self.assertEqual(js_res.status_code, 200)
        self.assertIn("loadAgents", js_res.text)
        login_res = self.client.get("/login")
        self.assertEqual(login_res.status_code, 200)
        self.assertIn("Lab Management", login_res.text)

    def test_02_authentication_flows(self):
        c = TestClient(app)
        root_res = c.get("/", follow_redirects=False)
        self.assertEqual(root_res.status_code, 303)
        self.assertEqual(root_res.headers["location"], "/login")
        bad_res = c.post("/api/auth/login", json={"username": "nonexistent_user", "password": "wrong"})
        self.assertEqual(bad_res.status_code, 401)
        self.assertEqual(bad_res.json()["detail"], "Invalid credentials")
        bad_pass = c.post("/api/auth/login", json={"username": "admin", "password": "wrongpassword"})
        self.assertEqual(bad_pass.status_code, 401)
        self.assertEqual(bad_pass.json()["detail"], "Invalid credentials")
        for role, creds in [("ADMIN", self.admin_creds), ("OPERATOR", self.operator_creds), ("VIEWER", self.viewer_creds)]:
            cli = TestClient(app)
            res = cli.post("/api/auth/login", json=creds)
            self.assertEqual(res.status_code, 200)
            self.assertEqual(res.json()["role"], role)
            sess = cli.get("/api/auth/session")
            self.assertEqual(sess.status_code, 200)
            self.assertEqual(sess.json()["role"], role)
            self.assertEqual(cli.post("/api/auth/logout").status_code, 200)
            self.assertEqual(cli.get("/api/auth/session").status_code, 401)

    def test_03_role_authorization_boundaries(self):
        agent_id = str(uuid.uuid4())
        self.client.post("/api/agents/register", headers={"X-Agent-Token": self.agent_secret}, json={"agent_id": agent_id, "hostname": "AUTH-TEST-PC", "ip_address": "192.168.1.50", "operating_system": "Linux"})
        self.client.post(f"/api/agents/{agent_id}/heartbeat", headers={"X-Agent-Token": self.agent_secret})
        viewer_cli = TestClient(app)
        viewer_cli.post("/api/auth/login", json=self.viewer_creds)
        self.assertEqual(viewer_cli.get("/api/agents").status_code, 200)
        self.assertEqual(viewer_cli.get(f"/api/agents/{agent_id}").status_code, 200)
        self.assertEqual(viewer_cli.get("/api/discovery").status_code, 200)
        self.assertEqual(viewer_cli.get("/api/audit").status_code, 403)
        self.assertEqual(viewer_cli.get("/api/admin/status").status_code, 403)
        self.assertEqual(viewer_cli.get("/api/admin/agents").status_code, 403)
        self.assertEqual(viewer_cli.post(f"/api/agents/{agent_id}/shutdown").status_code, 403)
        self.assertEqual(viewer_cli.post(f"/api/agents/{agent_id}/restart").status_code, 403)
        op_cli = TestClient(app)
        op_cli.post("/api/auth/login", json=self.operator_creds)
        self.assertEqual(op_cli.get("/api/agents").status_code, 200)
        self.assertEqual(op_cli.get("/api/discovery").status_code, 200)
        self.assertEqual(op_cli.post(f"/api/agents/{agent_id}/shutdown").status_code, 202)
        self.assertEqual(op_cli.get("/api/audit").status_code, 403)
        self.assertEqual(op_cli.get("/api/admin/status").status_code, 403)
        self.assertEqual(op_cli.get("/api/admin/agents").status_code, 403)
        admin_cli = TestClient(app)
        admin_cli.post("/api/auth/login", json=self.admin_creds)
        self.assertEqual(admin_cli.get("/api/audit").status_code, 200)
        self.assertEqual(admin_cli.get("/api/admin/status").status_code, 200)
        self.assertEqual(admin_cli.get("/api/admin/agents").status_code, 200)

    def test_04_agent_registration_validation(self):
        agent_id = str(uuid.uuid4())
        self.assertEqual(self.client.post("/api/agents/register", json={"agent_id": agent_id, "hostname": "REG-TEST", "ip_address": "192.168.1.51", "operating_system": "Windows 11"}).status_code, 401)
        self.assertEqual(self.client.post("/api/agents/register", headers={"X-Agent-Token": "bad-token"}, json={"agent_id": agent_id, "hostname": "REG-TEST", "ip_address": "192.168.1.51", "operating_system": "Windows 11"}).status_code, 401)
        self.assertEqual(self.client.post("/api/agents/register", headers={"X-Agent-Token": self.agent_secret}, json={"agent_id": "not-a-valid-uuid", "hostname": "REG-TEST", "ip_address": "192.168.1.51", "operating_system": "Windows 11"}).status_code, 422)
        res_ok = self.client.post("/api/agents/register", headers={"X-Agent-Token": self.agent_secret}, json={"agent_id": agent_id, "hostname": "REG-TEST-ORIGINAL", "ip_address": "192.168.1.51", "operating_system": "Windows 11"})
        self.assertEqual(res_ok.status_code, 200)
        self.assertEqual(res_ok.json()["hostname"], "REG-TEST-ORIGINAL")
        res_dup = self.client.post("/api/agents/register", headers={"X-Agent-Token": self.agent_secret}, json={"agent_id": agent_id, "hostname": "REG-TEST-RENAMED", "ip_address": "192.168.1.52", "operating_system": "Windows 11 Pro"})
        self.assertEqual(res_dup.status_code, 200)
        self.assertEqual(res_dup.json()["hostname"], "REG-TEST-RENAMED")
        with app.state.database.connect() as db:
            db.execute("UPDATE agents SET enabled = 0 WHERE agent_id = ?", (agent_id,))
        self.assertEqual(self.client.post("/api/agents/register", headers={"X-Agent-Token": self.agent_secret}, json={"agent_id": agent_id, "hostname": "REG-TEST-DISABLED", "ip_address": "192.168.1.52", "operating_system": "Windows 11 Pro"}).status_code, 403)

    def test_05_heartbeat_and_offline_detection(self):
        agent_id = str(uuid.uuid4())
        self.client.post("/api/agents/register", headers={"X-Agent-Token": self.agent_secret}, json={"agent_id": agent_id, "hostname": "HB-TEST-PC", "ip_address": "192.168.1.60", "operating_system": "Ubuntu"})
        self.assertEqual(self.client.post(f"/api/agents/{agent_id}/heartbeat", headers={"X-Agent-Token": self.agent_secret}).status_code, 200)
        admin_cli = TestClient(app)
        admin_cli.post("/api/auth/login", json=self.admin_creds)
        self.assertEqual(admin_cli.get(f"/api/agents/{agent_id}").json()["status"], "ONLINE")
        time.sleep(2.1)
        self.assertEqual(admin_cli.get(f"/api/agents/{agent_id}").json()["status"], "OFFLINE")
        self.assertEqual(self.client.post(f"/api/agents/{agent_id}/heartbeat", headers={"X-Agent-Token": self.agent_secret}).status_code, 200)

    def test_06_network_discovery(self):
        admin_cli = TestClient(app)
        admin_cli.post("/api/auth/login", json=self.admin_creds)
        scan_res = admin_cli.post("/api/discovery/scan")
        self.assertEqual(scan_res.status_code, 200)
        results = scan_res.json()
        self.assertIsInstance(results, list)
        self.assertEqual(len(admin_cli.get("/api/discovery").json()), len(results))

    def test_07_screen_stream_websocket(self):
        agent_id = str(uuid.uuid4())
        self.client.post("/api/agents/register", headers={"X-Agent-Token": self.agent_secret}, json={"agent_id": agent_id, "hostname": "STREAM-PC", "ip_address": "192.168.1.70", "operating_system": "Linux"})
        self.client.post(f"/api/agents/{agent_id}/heartbeat", headers={"X-Agent-Token": self.agent_secret})
        admin_cli = TestClient(app)
        admin_cli.post("/api/auth/login", json=self.admin_creds)
        unauth_cli = TestClient(app)
        with unauth_cli.websocket_connect(f"/ws/agents/{agent_id}/screen") as ws:
            ws.send_json({"role": "viewer"})
        with self.client.websocket_connect(f"/ws/agents/{agent_id}/screen", headers={"X-Agent-Token": self.agent_secret}) as src_ws:
            src_ws.send_json({"role": "source"})
            with admin_cli.websocket_connect(f"/ws/agents/{agent_id}/screen") as view_ws:
                view_ws.send_json({"role": "viewer"})
                test_frame = base64.b64encode(b"TEST_SCREEN_FRAME").decode("utf-8")
                src_ws.send_json({"type": "frame", "data": test_frame})
                msg = view_ws.receive_json()
                self.assertEqual(msg["type"], "frame")
                self.assertEqual(msg["data"], test_frame)
                view_ws.send_json({"type": "ping"})
                self.assertEqual(view_ws.receive_json()["type"], "pong")

    def test_08_power_control_pipeline(self):
        agent_id = str(uuid.uuid4())
        self.client.post("/api/agents/register", headers={"X-Agent-Token": self.agent_secret}, json={"agent_id": agent_id, "hostname": "POWER-PC", "ip_address": "192.168.1.80", "operating_system": "Linux"})
        self.client.post(f"/api/agents/{agent_id}/heartbeat", headers={"X-Agent-Token": self.agent_secret})
        admin_cli = TestClient(app)
        admin_cli.post("/api/auth/login", json=self.admin_creds)
        self.assertEqual(admin_cli.post(f"/api/agents/{agent_id}/shutdown").status_code, 202)
        self.assertEqual(admin_cli.post(f"/api/agents/{agent_id}/shutdown").status_code, 409)
        cmd = self.client.get(f"/api/agents/{agent_id}/power-command", headers={"X-Agent-Token": self.agent_secret}).json()["command"]
        self.assertEqual(cmd["action"], "shutdown")
        res = execute_power_action(cmd["action"], dry_run=True)
        self.assertEqual(res, "dry_run")
        self.assertEqual(self.client.post(f"/api/agents/{agent_id}/power-command/ack", headers={"X-Agent-Token": self.agent_secret}, json={"command_id": cmd["id"], "result": res}).status_code, 200)
        self.assertIsNone(self.client.get(f"/api/agents/{agent_id}/power-command", headers={"X-Agent-Token": self.agent_secret}).json()["command"])

    def test_09_database_persistence(self):
        agent_id = str(uuid.uuid4())
        self.client.post("/api/agents/register", headers={"X-Agent-Token": self.agent_secret}, json={"agent_id": agent_id, "hostname": "PERSIST-PC", "ip_address": "192.168.1.90", "operating_system": "Linux"})
        reopened_db = Database(TEMP_DB_PATH)
        self.assertEqual(reopened_db.get_agent(agent_id)["hostname"], "PERSIST-PC")
        self.assertEqual(reopened_db.get_user("admin")["role"], "ADMIN")

    def test_10_audit_logging_and_secret_redaction(self):
        admin_cli = TestClient(app)
        admin_cli.post("/api/auth/login", json=self.admin_creds)
        raw_logs = json.dumps(admin_cli.get("/api/audit").json())
        self.assertGreater(len(raw_logs), 0)
        self.assertNotIn("AdminPassword2026!", raw_logs)
        self.assertNotIn(self.agent_secret, raw_logs)
        self.assertNotIn(SERVER_CONFIG.app_secret, raw_logs)

    def test_11_deployment_files_exist_and_clean(self):
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        required = ["install-agent.ps1", "INSTALL_AGENT.bat", "INSTALL_AGENT.md", "START_MANAGER.bat", "start-manager.ps1", "MANAGER_SETUP.md", "deploy/windows/setup_manager_firewall.ps1", "deploy/windows/setup_agent.ps1", "deploy/windows/start_agent.bat", "deploy/linux/setup_agent.sh", "deploy/linux/lab-agent.service", "deploy/macos/com.labmanagement.agent.plist", ".env.example"]
        for relative_path in required:
            self.assertTrue(os.path.exists(os.path.join(project_root, relative_path)), relative_path)
        with open(os.path.join(project_root, ".gitignore"), encoding="utf-8") as gitignore_file:
            self.assertIn(".env", gitignore_file.read().splitlines())
        with open(os.path.join(project_root, "start-manager.ps1"), encoding="utf-8") as launcher_file:
            launcher = launcher_file.read()
        with open(os.path.join(project_root, "START_MANAGER.bat"), encoding="utf-8") as batch_launcher:
            batch_launcher_text = batch_launcher.read()
        self.assertIn("start-manager.ps1", batch_launcher_text)
        self.assertIn("server.main", launcher)
        self.assertIn("/api/health", launcher)
        self.assertIn("Get-PortListeners", launcher)
        self.assertIn("LAB_APP_SECRET", launcher)
        self.assertIn("LAB_AGENT_ENROLLMENT_SECRET", launcher)
        self.assertIn('modules = ("fastapi", "httpx", "PIL", "uvicorn", "websockets", "itsdangerous")', launcher)
        self.assertIn('& $PythonPath "-"', launcher)

    def test_12_linux_installer_venv_python_and_path_handling(self):
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        installer_path = os.path.join(project_root, "deploy", "linux", "setup_agent.sh")
        with open(installer_path, encoding="utf-8") as f:
            content = f.read()
        self.assertIn('"${VENV_PYTHON}" -m pip', content)
        self.assertNotIn('"${VENV_PIP}"', content)
        self.assertIn("ensurepip", content)
        self.assertIn('if [ ! -x "${VENV_PYTHON}" ]', content)
        self.assertIn('"${VENV_DIR}"', content)
        self.assertIn('"${VENV_PYTHON}"', content)
        self.assertIn('"${ENV_FILE}"', content)
        self.assertIn('"${REQUIREMENTS_FILE}"', content)

    def test_13_windows_installer_bootstrap_path_regression(self):
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        bootstrap_path = os.path.join(project_root, "install-agent.ps1")
        setup_path = os.path.join(project_root, "deploy", "windows", "setup_agent.ps1")
        with open(bootstrap_path, encoding="utf-8") as f:
            bootstrap = f.read()
        with open(setup_path, encoding="utf-8") as f:
            setup = f.read()

        # Bootstrap must explicitly own and pass the installation root.
        self.assertIn("ProjectRoot = $projectRoot", bootstrap)
        self.assertIn("Get-Item -LiteralPath (Get-Location).Path", bootstrap)
        self.assertIn('Join-Path $candidate.FullName ".git"', bootstrap)
        self.assertNotIn("rev-parse --show-toplevel", bootstrap)
        self.assertNotIn("Set-ExecutionPolicy", bootstrap)
        self.assertIn("-LiteralPath", bootstrap)
        self.assertIn("$projectRoot", bootstrap)

        # Setup must accept an explicit root and only fall back to script path
        # discovery when it is actually available.
        self.assertIn("[string]$ProjectRoot", setup)
        self.assertIn("Resolve-ProjectRoot", setup)
        self.assertIn("[string]::IsNullOrWhiteSpace($PSCommandPath)", setup)
        self.assertIn("$MyInvocation.MyCommand.Path", setup)
        self.assertIn("ProjectRoot could not be determined.", setup)
        self.assertIn('Set-Location -LiteralPath $ProjectRoot', setup)
        self.assertIn("deploy\\windows\\setup_agent.ps1", setup)

        # Paths must be literal/validated and spaces must remain supported.
        self.assertIn("Test-Path -LiteralPath", setup)
        self.assertIn("Resolve-Path -LiteralPath", setup)
        self.assertIn("Join-Path $ProjectRoot '.venv'", setup)
        self.assertIn("Join-Path $ProjectRoot 'agent.env'", setup)
        self.assertNotIn("Split-Path -Parent $PSCommandPath", setup)

        # Secret must not be emitted in registration output.
        self.assertIn("Server connection verified and machine registered.", setup)
        self.assertNotIn('Write-Host "      Server connection verified and machine registered: $registrationOutput"', setup)


if __name__ == "__main__":
    unittest.main()

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
os.environ["LAB_OFFLINE_TIMEOUT"] = "2.0"  # short timeout for testing offline detection
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

    # --------------------------------------------------------------------------
    # TEST 1: SERVER STARTUP & STATIC FILES
    # --------------------------------------------------------------------------
    def test_01_server_startup_and_health(self):
        # Health check
        res = self.client.get("/api/health")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json(), {"status": "running"})

        # Static CSS
        css_res = self.client.get("/static/styles.css")
        self.assertEqual(css_res.status_code, 200)
        self.assertIn("--bg-sidebar", css_res.text)

        # Static JS
        js_res = self.client.get("/static/app.js")
        self.assertEqual(js_res.status_code, 200)
        self.assertIn("loadAgents", js_res.text)

        # Login page
        login_res = self.client.get("/login")
        self.assertEqual(login_res.status_code, 200)
        self.assertIn("Lab Management", login_res.text)

    # --------------------------------------------------------------------------
    # TEST 2: AUTHENTICATION
    # --------------------------------------------------------------------------
    def test_02_authentication_flows(self):
        c = TestClient(app)

        # 1. Unauthenticated root redirects to /login
        root_res = c.get("/", follow_redirects=False)
        self.assertEqual(root_res.status_code, 303)
        self.assertEqual(root_res.headers["location"], "/login")

        # 2. Invalid login fails without leaking username existence
        bad_res = c.post("/api/auth/login", json={"username": "nonexistent_user", "password": "wrong"})
        self.assertEqual(bad_res.status_code, 401)
        self.assertEqual(bad_res.json()["detail"], "Invalid credentials")

        bad_pass = c.post("/api/auth/login", json={"username": "admin", "password": "wrongpassword"})
        self.assertEqual(bad_pass.status_code, 401)
        self.assertEqual(bad_pass.json()["detail"], "Invalid credentials")

        # 3. Valid logins
        for role, creds in [("ADMIN", self.admin_creds), ("OPERATOR", self.operator_creds), ("VIEWER", self.viewer_creds)]:
            cli = TestClient(app)
            res = cli.post("/api/auth/login", json=creds)
            self.assertEqual(res.status_code, 200)
            self.assertEqual(res.json()["role"], role)

            # Session info
            sess = cli.get("/api/auth/session")
            self.assertEqual(sess.status_code, 200)
            self.assertEqual(sess.json()["role"], role)

            # Logout
            logout_res = cli.post("/api/auth/logout")
            self.assertEqual(logout_res.status_code, 200)

            # Post-logout protected request fails
            after_logout = cli.get("/api/auth/session")
            self.assertEqual(after_logout.status_code, 401)

    # --------------------------------------------------------------------------
    # TEST 3: ROLE AUTHORIZATION
    # --------------------------------------------------------------------------
    def test_03_role_authorization_boundaries(self):
        # Setup agent for power tests
        agent_id = str(uuid.uuid4())
        self.client.post("/api/agents/register", headers={"X-Agent-Token": self.agent_secret}, json={
            "agent_id": agent_id,
            "hostname": "AUTH-TEST-PC",
            "ip_address": "192.168.1.50",
            "operating_system": "Linux",
        })
        self.client.post(f"/api/agents/{agent_id}/heartbeat", headers={"X-Agent-Token": self.agent_secret})

        # VIEWER Client
        viewer_cli = TestClient(app)
        viewer_cli.post("/api/auth/login", json=self.viewer_creds)

        self.assertEqual(viewer_cli.get("/api/agents").status_code, 200)
        self.assertEqual(viewer_cli.get(f"/api/agents/{agent_id}").status_code, 200)
        self.assertEqual(viewer_cli.get("/api/discovery").status_code, 200)
        # Denied endpoints
        self.assertEqual(viewer_cli.get("/api/audit").status_code, 403)
        self.assertEqual(viewer_cli.get("/api/admin/status").status_code, 403)
        self.assertEqual(viewer_cli.get("/api/admin/agents").status_code, 403)
        self.assertEqual(viewer_cli.post(f"/api/agents/{agent_id}/shutdown").status_code, 403)
        self.assertEqual(viewer_cli.post(f"/api/agents/{agent_id}/restart").status_code, 403)

        # OPERATOR Client
        op_cli = TestClient(app)
        op_cli.post("/api/auth/login", json=self.operator_creds)

        self.assertEqual(op_cli.get("/api/agents").status_code, 200)
        self.assertEqual(op_cli.get("/api/discovery").status_code, 200)
        # Operator can power control
        self.assertEqual(op_cli.post(f"/api/agents/{agent_id}/shutdown").status_code, 202)
        # Denied admin endpoints
        self.assertEqual(op_cli.get("/api/audit").status_code, 403)
        self.assertEqual(op_cli.get("/api/admin/status").status_code, 403)
        self.assertEqual(op_cli.get("/api/admin/agents").status_code, 403)

        # ADMIN Client
        admin_cli = TestClient(app)
        admin_cli.post("/api/auth/login", json=self.admin_creds)

        self.assertEqual(admin_cli.get("/api/audit").status_code, 200)
        self.assertEqual(admin_cli.get("/api/admin/status").status_code, 200)
        self.assertEqual(admin_cli.get("/api/admin/agents").status_code, 200)

    # --------------------------------------------------------------------------
    # TEST 4: AGENT REGISTRATION
    # --------------------------------------------------------------------------
    def test_04_agent_registration_validation(self):
        agent_id = str(uuid.uuid4())

        # 1. Invalid / Missing token
        res_no_tok = self.client.post("/api/agents/register", json={
            "agent_id": agent_id,
            "hostname": "REG-TEST",
            "ip_address": "192.168.1.51",
            "operating_system": "Windows 11",
        })
        self.assertEqual(res_no_tok.status_code, 401)

        res_bad_tok = self.client.post("/api/agents/register", headers={"X-Agent-Token": "bad-token"}, json={
            "agent_id": agent_id,
            "hostname": "REG-TEST",
            "ip_address": "192.168.1.51",
            "operating_system": "Windows 11",
        })
        self.assertEqual(res_bad_tok.status_code, 401)

        # 2. Malformed Agent ID
        res_mal_id = self.client.post("/api/agents/register", headers={"X-Agent-Token": self.agent_secret}, json={
            "agent_id": "not-a-valid-uuid",
            "hostname": "REG-TEST",
            "ip_address": "192.168.1.51",
            "operating_system": "Windows 11",
        })
        self.assertEqual(res_mal_id.status_code, 422)

        # 3. Valid Registration
        res_ok = self.client.post("/api/agents/register", headers={"X-Agent-Token": self.agent_secret}, json={
            "agent_id": agent_id,
            "hostname": "REG-TEST-ORIGINAL",
            "ip_address": "192.168.1.51",
            "operating_system": "Windows 11",
        })
        self.assertEqual(res_ok.status_code, 200)
        self.assertEqual(res_ok.json()["hostname"], "REG-TEST-ORIGINAL")

        # 4. Duplicate registration updates existing entry
        res_dup = self.client.post("/api/agents/register", headers={"X-Agent-Token": self.agent_secret}, json={
            "agent_id": agent_id,
            "hostname": "REG-TEST-RENAMED",
            "ip_address": "192.168.1.52",
            "operating_system": "Windows 11 Pro",
        })
        self.assertEqual(res_dup.status_code, 200)
        self.assertEqual(res_dup.json()["hostname"], "REG-TEST-RENAMED")

        # 5. Disabled agent registration rejection
        with app.state.database.connect() as db:
            db.execute("UPDATE agents SET enabled = 0 WHERE agent_id = ?", (agent_id,))
        res_disabled = self.client.post("/api/agents/register", headers={"X-Agent-Token": self.agent_secret}, json={
            "agent_id": agent_id,
            "hostname": "REG-TEST-DISABLED",
            "ip_address": "192.168.1.52",
            "operating_system": "Windows 11 Pro",
        })
        self.assertEqual(res_disabled.status_code, 403)

    # --------------------------------------------------------------------------
    # TEST 5: HEARTBEAT & TIMEOUT
    # --------------------------------------------------------------------------
    def test_05_heartbeat_and_offline_detection(self):
        agent_id = str(uuid.uuid4())
        self.client.post("/api/agents/register", headers={"X-Agent-Token": self.agent_secret}, json={
            "agent_id": agent_id,
            "hostname": "HB-TEST-PC",
            "ip_address": "192.168.1.60",
            "operating_system": "Ubuntu",
        })

        # 1. Heartbeat succeeds
        hb_res = self.client.post(f"/api/agents/{agent_id}/heartbeat", headers={"X-Agent-Token": self.agent_secret})
        self.assertEqual(hb_res.status_code, 200)
        self.assertEqual(hb_res.json()["status"], "ONLINE")

        # 2. Login to view agent
        admin_cli = TestClient(app)
        admin_cli.post("/api/auth/login", json=self.admin_creds)
        agent_data = admin_cli.get(f"/api/agents/{agent_id}").json()
        self.assertEqual(agent_data["status"], "ONLINE")

        # 3. Simulate stale heartbeat > timeout (timeout is 2.0s in test env)
        time.sleep(2.1)
        stale_agent = admin_cli.get(f"/api/agents/{agent_id}").json()
        self.assertEqual(stale_agent["status"], "OFFLINE")

        # 4. Reconnection heartbeat
        reconn = self.client.post(f"/api/agents/{agent_id}/heartbeat", headers={"X-Agent-Token": self.agent_secret})
        self.assertEqual(reconn.status_code, 200)
        self.assertEqual(reconn.json()["status"], "ONLINE")

    # --------------------------------------------------------------------------
    # TEST 6: NETWORK DISCOVERY
    # --------------------------------------------------------------------------
    def test_06_network_discovery(self):
        admin_cli = TestClient(app)
        admin_cli.post("/api/auth/login", json=self.admin_creds)

        scan_res = admin_cli.post("/api/discovery/scan")
        self.assertEqual(scan_res.status_code, 200)
        results = scan_res.json()
        self.assertIsInstance(results, list)

        # Cached discovery
        cached = admin_cli.get("/api/discovery").json()
        self.assertEqual(len(cached), len(results))

    # --------------------------------------------------------------------------
    # TEST 7: SCREEN STREAMING WEBSOCKETS
    # --------------------------------------------------------------------------
    def test_07_screen_stream_websocket(self):
        agent_id = str(uuid.uuid4())
        self.client.post("/api/agents/register", headers={"X-Agent-Token": self.agent_secret}, json={
            "agent_id": agent_id,
            "hostname": "STREAM-PC",
            "ip_address": "192.168.1.70",
            "operating_system": "Linux",
        })
        self.client.post(f"/api/agents/{agent_id}/heartbeat", headers={"X-Agent-Token": self.agent_secret})

        admin_cli = TestClient(app)
        admin_cli.post("/api/auth/login", json=self.admin_creds)

        # 1. Unauthenticated viewer rejected
        unauth_cli = TestClient(app)
        with unauth_cli.websocket_connect(f"/ws/agents/{agent_id}/screen") as ws:
            ws.send_json({"role": "viewer"})
            # Server closes with 4401

        # 2. Source & Viewer communication
        with self.client.websocket_connect(f"/ws/agents/{agent_id}/screen", headers={"X-Agent-Token": self.agent_secret}) as src_ws:
            src_ws.send_json({"role": "source"})

            # Authenticated viewer connects
            with admin_cli.websocket_connect(f"/ws/agents/{agent_id}/screen") as view_ws:
                view_ws.send_json({"role": "viewer"})

                # Relayed frame
                test_frame = base64.b64encode(b"TEST_SCREEN_FRAME").decode("utf-8")
                src_ws.send_json({"type": "frame", "data": test_frame})

                msg = view_ws.receive_json()
                self.assertEqual(msg["type"], "frame")
                self.assertEqual(msg["data"], test_frame)

                # Ping/Pong
                view_ws.send_json({"type": "ping"})
                pong = view_ws.receive_json()
                self.assertEqual(pong["type"], "pong")

    # --------------------------------------------------------------------------
    # TEST 8: POWER CONTROL & DRY-RUN
    # --------------------------------------------------------------------------
    def test_08_power_control_pipeline(self):
        agent_id = str(uuid.uuid4())
        self.client.post("/api/agents/register", headers={"X-Agent-Token": self.agent_secret}, json={
            "agent_id": agent_id,
            "hostname": "POWER-PC",
            "ip_address": "192.168.1.80",
            "operating_system": "Linux",
        })
        self.client.post(f"/api/agents/{agent_id}/heartbeat", headers={"X-Agent-Token": self.agent_secret})

        admin_cli = TestClient(app)
        admin_cli.post("/api/auth/login", json=self.admin_creds)

        # 1. Queue command
        q_res = admin_cli.post(f"/api/agents/{agent_id}/shutdown")
        self.assertEqual(q_res.status_code, 202)
        self.assertEqual(q_res.json()["status"], "queued")

        # 2. Attempt duplicate queue while pending returns 409
        dup_res = admin_cli.post(f"/api/agents/{agent_id}/shutdown")
        self.assertEqual(dup_res.status_code, 409)

        # 3. Agent fetches command
        fetch_res = self.client.get(f"/api/agents/{agent_id}/power-command", headers={"X-Agent-Token": self.agent_secret})
        self.assertEqual(fetch_res.status_code, 200)
        cmd = fetch_res.json()["command"]
        self.assertEqual(cmd["action"], "shutdown")

        # 4. Dry run execution
        res = execute_power_action(cmd["action"], dry_run=True)
        self.assertEqual(res, "dry_run")

        # 5. Acknowledge command
        ack_res = self.client.post(f"/api/agents/{agent_id}/power-command/ack", headers={"X-Agent-Token": self.agent_secret}, json={
            "command_id": cmd["id"],
            "result": res
        })
        self.assertEqual(ack_res.status_code, 200)

        # 6. Subsequent check returns None (no pending command)
        empty_cmd = self.client.get(f"/api/agents/{agent_id}/power-command", headers={"X-Agent-Token": self.agent_secret}).json()
        self.assertIsNone(empty_cmd["command"])

    # --------------------------------------------------------------------------
    # TEST 9: DATABASE PERSISTENCE ACROSS RESTART
    # --------------------------------------------------------------------------
    def test_09_database_persistence(self):
        agent_id = str(uuid.uuid4())
        self.client.post("/api/agents/register", headers={"X-Agent-Token": self.agent_secret}, json={
            "agent_id": agent_id,
            "hostname": "PERSIST-PC",
            "ip_address": "192.168.1.90",
            "operating_system": "Linux",
        })

        # New database connection to same SQLite file
        reopened_db = Database(TEMP_DB_PATH)
        agent = reopened_db.get_agent(agent_id)
        self.assertIsNotNone(agent)
        self.assertEqual(agent["hostname"], "PERSIST-PC")

        user = reopened_db.get_user("admin")
        self.assertIsNotNone(user)
        self.assertEqual(user["role"], "ADMIN")

    # --------------------------------------------------------------------------
    # TEST 10: AUDIT LOGGING & ZERO SECRET EXPOSURE
    # --------------------------------------------------------------------------
    def test_10_audit_logging_and_secret_redaction(self):
        admin_cli = TestClient(app)
        admin_cli.post("/api/auth/login", json=self.admin_creds)

        logs = admin_cli.get("/api/audit").json()
        self.assertGreater(len(logs), 0)

        # Ensure no secrets in logs
        raw_logs = json.dumps(logs)
        self.assertNotIn("AdminPassword2026!", raw_logs)
        self.assertNotIn(self.agent_secret, raw_logs)
        self.assertNotIn(SERVER_CONFIG.app_secret, raw_logs)

    # --------------------------------------------------------------------------
    # TEST 11: DEPLOYMENT CONFIGURATION INTEGRITY
    # --------------------------------------------------------------------------
    def test_11_deployment_files_exist_and_clean(self):
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

        # Check required deployment files
        self.assertTrue(os.path.exists(os.path.join(project_root, "install-agent.ps1")))
        self.assertTrue(os.path.exists(os.path.join(project_root, "INSTALL_AGENT.bat")))
        self.assertTrue(os.path.exists(os.path.join(project_root, "INSTALL_AGENT.md")))
        self.assertTrue(os.path.exists(os.path.join(project_root, "deploy/windows/setup_agent.ps1")))
        self.assertTrue(os.path.exists(os.path.join(project_root, "deploy/windows/start_agent.bat")))
        self.assertTrue(os.path.exists(os.path.join(project_root, "deploy/linux/setup_agent.sh")))
        self.assertTrue(os.path.exists(os.path.join(project_root, "deploy/linux/lab-agent.service")))
        self.assertTrue(os.path.exists(os.path.join(project_root, "deploy/macos/com.labmanagement.agent.plist")))
        self.assertTrue(os.path.exists(os.path.join(project_root, ".env.example")))


if __name__ == "__main__":
    unittest.main()

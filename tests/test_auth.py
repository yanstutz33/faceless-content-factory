import json
import sqlite3
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from contextlib import closing
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

from factory.auth import LocalAuth
from factory.config import Settings
from factory.pipeline import Pipeline
from factory.store import Store
from factory.web import create_server
from factory.workspace_lifecycle import WorkspaceLifecycle
from factory.workspaces import WorkspaceRegistry


ROOT = Path(__file__).parents[1]
PASSWORD = "correct horse battery staple"


class LocalAuthTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.auth = LocalAuth(self.root / "access.sqlite3")
        self.admin = self.auth.bootstrap_admin("owner", PASSWORD, "alpha")
        self.admin_session = self.auth.session(
            self.auth.login("owner", PASSWORD, "alpha")["session_token"]
        )
        assert self.admin_session is not None

    def tearDown(self):
        self.temporary.cleanup()

    def test_roles_prevent_self_elevation_and_scope_account_listing(self):
        editor = self.auth.create_user(self.admin_session, "editor", PASSWORD, "editor")
        reviewer = self.auth.create_user(self.admin_session, "reviewer", PASSWORD, "reviewer")
        editor_login = self.auth.login("editor", PASSWORD, "alpha")
        editor_session = self.auth.session(editor_login["session_token"])
        assert editor_session is not None
        with self.assertRaises(PermissionError):
            self.auth.create_user(editor_session, "intruder", PASSWORD, "admin")
        with self.assertRaises(PermissionError):
            self.auth.grant_workspace(editor_session, editor["id"], "alpha", "admin")
        self.assertEqual(
            [(item["username"], item["role"]) for item in self.auth.list_users(self.admin_session)],
            [("editor", "editor"), ("owner", "admin"), ("reviewer", "reviewer")],
        )
        self.assertEqual(reviewer["role"], "reviewer")

    def test_workspace_selection_requires_membership_and_refreshes_role(self):
        editor = self.auth.create_user(self.admin_session, "editor", PASSWORD, "editor")
        self.auth.bootstrap_admin("beta-owner", PASSWORD, "beta")
        beta_token = self.auth.login("beta-owner", PASSWORD, "beta")["session_token"]
        beta_admin = self.auth.session(beta_token)
        assert beta_admin is not None
        self.auth.grant_workspace(beta_admin, editor["id"], "beta", "reviewer")
        token = self.auth.login("editor", PASSWORD, "alpha")["session_token"]
        selected = self.auth.select_workspace(token, "beta")
        self.assertEqual((selected["workspace_id"], selected["role"]), ("beta", "reviewer"))
        with self.assertRaises(PermissionError):
            self.auth.select_workspace(token, "gamma")
        self.assertEqual(self.auth.session(token)["workspace_id"], "beta")

    def test_lockout_expires_and_success_resets_attempts(self):
        for _ in range(5):
            with self.assertRaises(ValueError):
                self.auth.login("owner", "wrong password value", "alpha")
        with self.assertRaisesRegex(ValueError, "temporariamente bloqueado"):
            self.auth.login("owner", PASSWORD, "alpha")
        with closing(sqlite3.connect(self.auth.database)) as db:
            db.execute("UPDATE auth_users SET locked_until=? WHERE username='owner'",
                       ((datetime.now(UTC) - timedelta(seconds=1)).isoformat(),))
            db.commit()
        self.auth.login("owner", PASSWORD, "alpha")
        with closing(sqlite3.connect(self.auth.database)) as db:
            attempts, locked_until = db.execute(
                "SELECT failed_attempts,locked_until FROM auth_users WHERE username='owner'"
            ).fetchone()
        self.assertEqual(attempts, 0)
        self.assertIsNone(locked_until)

    def test_recovery_is_one_time_expires_and_revokes_sessions(self):
        editor = self.auth.create_user(self.admin_session, "editor", PASSWORD, "editor")
        active = self.auth.login("editor", PASSWORD, "alpha")["session_token"]
        issued = self.auth.issue_recovery(self.admin_session, "editor")
        changed = self.auth.recover(issued["recovery_token"], "a new and stronger password")
        self.assertTrue(changed["sessions_revoked"])
        self.assertIsNone(self.auth.session(active))
        with self.assertRaisesRegex(ValueError, "já utilizado"):
            self.auth.recover(issued["recovery_token"], "another strong password")
        expired = self.auth.issue_recovery(self.admin_session, "editor")
        with closing(sqlite3.connect(self.auth.database)) as db:
            db.execute("UPDATE auth_recovery_tokens SET expires_at=? WHERE token_hash=(SELECT token_hash FROM auth_recovery_tokens WHERE used_at IS NULL)",
                       ((datetime.now(UTC) - timedelta(seconds=1)).isoformat(),))
            db.commit()
        with self.assertRaisesRegex(ValueError, "expirado"):
            self.auth.recover(expired["recovery_token"], "yet another strong password")
        self.assertTrue(editor["id"])

    def test_absolute_expiry_and_logout_revoke_opaque_session(self):
        login = self.auth.login("owner", PASSWORD, "alpha")
        token = login["session_token"]
        self.assertNotIn(token, self.auth.database.read_bytes().decode("latin-1"))
        self.assertTrue(self.auth.logout(token))
        self.assertIsNone(self.auth.session(token))
        other = self.auth.login("owner", PASSWORD, "alpha")["session_token"]
        with closing(sqlite3.connect(self.auth.database)) as db:
            db.execute("UPDATE auth_sessions SET expires_at=? WHERE revoked_at IS NULL",
                       ((datetime.now(UTC) - timedelta(seconds=1)).isoformat(),))
            db.commit()
        self.assertIsNone(self.auth.session(other))


class AuthenticatedServerTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        root = Path(self.temporary.name)
        self.registry = WorkspaceRegistry(root / "data")
        self.context = self.registry.provision("alpha", "Client Alpha")
        settings = Settings(root, root / "data", "ffmpeg", "ffprobe", "127.0.0.1", 0, False)
        settings = replace(self.context.scoped_settings(settings), local_auth=True,
                           calendar_poll_seconds=300)
        self.store = Store(settings.data_dir / "factory.sqlite3")
        self.pipeline = Pipeline(settings, self.store)
        self.auth = LocalAuth(root / "private" / "access.sqlite3")
        admin = self.auth.bootstrap_admin("owner", PASSWORD, "alpha")
        admin_login = self.auth.login("owner", PASSWORD, "alpha")
        admin_session = self.auth.session(admin_login["session_token"])
        assert admin_session is not None
        self.auth.create_user(admin_session, "editor", PASSWORD, "editor")
        self.auth.create_user(admin_session, "reviewer", PASSWORD, "reviewer")
        self.server = create_server(
            self.pipeline, self.store, "127.0.0.1", 0, ROOT / "web",
            auth=self.auth, workspace_id="alpha", operational_dir=root / "private",
            lifecycle=WorkspaceLifecycle(self.registry),
        )
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.server.server_address[1]}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.temporary.cleanup()

    def request(self, path, *, method="GET", data=None, cookie="", csrf=""):
        headers = {"Origin": self.base}
        if cookie:
            headers["Cookie"] = cookie
        if csrf:
            headers["X-CSRF-Token"] = csrf
        payload = None
        if data is not None:
            payload = json.dumps(data).encode()
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(self.base + path, data=payload, headers=headers, method=method)
        try:
            response = urllib.request.urlopen(request)
        except urllib.error.HTTPError as exc:
            try:
                return exc.code, json.loads(exc.read()), dict(exc.headers)
            finally:
                exc.close()
        with response:
            body = response.read()
            return response.status, json.loads(body) if body else {}, dict(response.headers)

    def login(self, username):
        status, body, headers = self.request(
            "/api/auth/login", method="POST",
            data={"username": username, "password": PASSWORD, "workspace_id": "alpha"},
        )
        self.assertEqual(status, 200)
        set_cookie = headers["Set-Cookie"]
        return set_cookie.split(";", 1)[0], body["csrf_token"], set_cookie, body

    def test_cookie_csrf_logout_and_session_revocation(self):
        status, body, _ = self.request("/api/dashboard")
        self.assertEqual((status, body["code"]), (401, "LOGIN_REQUIRED"))
        cookie, csrf, set_cookie, login = self.login("owner")
        self.assertIn("HttpOnly", set_cookie)
        self.assertIn("SameSite=Strict", set_cookie)
        self.assertNotIn("session_token", login)
        status, body, _ = self.request("/api/not-a-route", method="POST", data={}, cookie=cookie)
        self.assertEqual((status, body["code"]), (403, "CSRF_REQUIRED"))
        status, body, _ = self.request(
            "/api/auth/logout", method="POST", data={}, cookie=cookie, csrf=csrf
        )
        self.assertEqual((status, body["logged_out"]), (200, True))
        status, body, _ = self.request("/api/dashboard", cookie=cookie)
        self.assertEqual((status, body["code"]), (401, "LOGIN_REQUIRED"))

    def test_roles_guard_every_mutation_before_dispatch(self):
        editor_cookie, editor_csrf, _, _ = self.login("editor")
        reviewer_cookie, reviewer_csrf, _, _ = self.login("reviewer")
        status, body, _ = self.request(
            "/api/auth/users", method="POST",
            data={"username": "elevated", "password": PASSWORD, "role": "admin"},
            cookie=editor_cookie, csrf=editor_csrf,
        )
        self.assertEqual((status, body["code"]), (403, "ROLE_FORBIDDEN"))
        status, body, _ = self.request(
            "/api/jobs", method="POST", data={"topic": "blocked"},
            cookie=reviewer_cookie, csrf=reviewer_csrf,
        )
        self.assertEqual((status, body["code"]), (403, "ROLE_FORBIDDEN"))
        status, body, _ = self.request(
            "/api/jobs/missing/approve", method="POST", data={},
            cookie=editor_cookie, csrf=editor_csrf,
        )
        self.assertEqual((status, body["code"]), (403, "ROLE_FORBIDDEN"))
        status, body, _ = self.request(
            "/api/jobs/missing/approve", method="POST", data={},
            cookie=reviewer_cookie, csrf=reviewer_csrf,
        )
        self.assertNotEqual(body.get("code"), "ROLE_FORBIDDEN")

    def test_workspace_instance_boundary_and_admin_account_listing(self):
        status, body, _ = self.request(
            "/api/auth/login", method="POST",
            data={"username": "owner", "password": PASSWORD, "workspace_id": "beta"},
        )
        self.assertEqual((status, body["code"]), (409, "WORKSPACE_PROCESS_REQUIRED"))
        cookie, _, _, _ = self.login("owner")
        status, body, _ = self.request("/api/auth/users", cookie=cookie)
        self.assertEqual(status, 200)
        self.assertEqual({item["role"] for item in body}, {"admin", "editor", "reviewer"})

    def test_lifecycle_requires_admin_and_csrf_and_redacts_local_paths(self):
        editor_cookie, _, _, _ = self.login("editor")
        status, body, _ = self.request("/api/workspace/lifecycle/status", cookie=editor_cookie)
        self.assertEqual((status, body["code"]), (403, "ROLE_FORBIDDEN"))
        admin_cookie, admin_csrf, _, _ = self.login("owner")
        status, body, _ = self.request("/api/workspace/lifecycle/status", cookie=admin_cookie)
        self.assertEqual((status, body["workspace"]["id"]), (200, "alpha"))
        status, body, _ = self.request(
            "/api/workspace/lifecycle/demo-seed", method="POST", data={}, cookie=admin_cookie
        )
        self.assertEqual((status, body["code"]), (403, "CSRF_REQUIRED"))
        status, body, _ = self.request(
            "/api/workspace/lifecycle/demo-seed", method="POST", data={},
            cookie=admin_cookie, csrf=admin_csrf,
        )
        self.assertEqual((status, body["seeded"]), (201, True))
        status, body, _ = self.request(
            "/api/workspace/lifecycle/export", method="POST", data={"request_id": "api-export"},
            cookie=admin_cookie, csrf=admin_csrf,
        )
        self.assertEqual(status, 201)
        self.assertEqual(body["archive_name"], "alpha-api-export.zip")
        self.assertNotIn("archive", body)

    def test_personal_workspace_never_exposes_lifecycle_routes_or_ui(self):
        self.auth.bootstrap_admin("personal-owner", PASSWORD, "3am-shelter")
        handler = self.server.RequestHandlerClass
        handler.workspace_id = "3am-shelter"
        try:
            status, login, headers = self.request(
                "/api/auth/login", method="POST",
                data={"username": "personal-owner", "password": PASSWORD,
                      "workspace_id": "3am-shelter"},
            )
            self.assertEqual(status, 200)
            cookie = headers["Set-Cookie"].split(";", 1)[0]
            status, body, _ = self.request("/api/workspace/lifecycle/status", cookie=cookie)
            self.assertEqual((status, body["code"]), (404, "NOT_FOUND"))
        finally:
            handler.workspace_id = "alpha"
        app = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
        self.assertIn("state.auth.workspace_id==='3am-shelter'", app)

    def test_delete_requires_password_and_literal_confirmation_then_stops_instance(self):
        cookie, csrf, _, _ = self.login("owner")
        status, body, _ = self.request(
            "/api/workspace/lifecycle/delete", method="POST",
            data={"confirmation": "DELETE:alpha"}, cookie=cookie, csrf=csrf,
        )
        self.assertEqual((status, body["code"]), (401, "REAUTH_REQUIRED"))
        self.assertTrue(self.context.data_dir.exists())
        status, body, _ = self.request(
            "/api/workspace/lifecycle/delete", method="POST",
            data={"confirmation": "DELETE:alpha", "password": "wrong password value"},
            cookie=cookie, csrf=csrf,
        )
        self.assertEqual((status, body["code"]), (401, "REAUTH_FAILED"))
        self.assertTrue(self.context.data_dir.exists())
        status, body, _ = self.request(
            "/api/workspace/lifecycle/delete", method="POST",
            data={"confirmation": "DELETE:alpha", "password": PASSWORD},
            cookie=cookie, csrf=csrf,
        )
        self.assertEqual(status, 200)
        self.assertEqual(body["workspace_id"], "alpha")
        self.assertFalse(self.context.data_dir.exists())
        self.assertRegex(body["backup_sha256"], r"^[a-f0-9]{64}$")


if __name__ == "__main__":
    unittest.main()

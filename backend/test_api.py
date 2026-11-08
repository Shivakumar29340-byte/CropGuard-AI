"""Automated API tests.  Run with:  python test_api.py
Uses a temporary database, so your real cropguard.db is never touched."""
import os
import sqlite3
import tempfile
import unittest
from contextlib import closing
from unittest import mock

from app import create_app

class TrackedConnection(sqlite3.Connection):
    """A normal SQLite connection that remembers whether close() was called."""
    closed = False

    def close(self):
        self.closed = True
        super().close()


GOOD = {"name": "Asha Rao", "email": "Asha@Example.com", "password": "Farm1234"}


class ApiTests(unittest.TestCase):
    def setUp(self):
        fd, self.path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        # Record every SQLite connection made during this test (by the app and by the
        # test itself) so tearDown can prove each one was closed.
        self.connections = []
        real_connect = sqlite3.connect

        def tracked_connect(*args, **kwargs):
            conn = real_connect(*args, factory=TrackedConnection, **kwargs)
            self.connections.append(conn)
            return conn

        patcher = mock.patch("sqlite3.connect", tracked_connect)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.app = create_app({"DATABASE": self.path, "TESTING": True})
        self.c = self.app.test_client()

    def tearDown(self):
        # 1. Find connections that were never closed (the cause of WinError 32 on Windows).
        leaked = [c for c in self.connections if not c.closed]
        # 2. Close them so the file can be deleted, then delete it. If this still
        #    raises, the error is shown, not hidden.
        for conn in leaked:
            conn.close()
        os.remove(self.path)
        # 3. Fail the test loudly if anything leaked, on every operating system.
        self.assertEqual(len(leaked), 0, f"{len(leaked)} SQLite connection(s) were not closed")

    # helpers
    def query(self, sql):
        """Read from the test database and ALWAYS close the connection.
        An open connection keeps the file locked on Windows (WinError 32)."""
        with closing(sqlite3.connect(self.path)) as conn:
            return conn.execute(sql).fetchall()

    def register(self, **over):
        return self.c.post("/api/auth/register", json={**GOOD, **over})

    def login(self, email=GOOD["email"], password=GOOD["password"]):
        return self.c.post("/api/auth/login", json={"email": email, "password": password})

    def headers(self):
        self.register()
        token = self.login().get_json()["token"]
        return {"Authorization": f"Bearer {token}"}

    def det(self, **over):
        return {"crop": "tomato", "disease": "Early blight", "confidence": 0.93, "notes": "lower leaves", **over}

    # registration
    def test_register_ok_and_email_lowercased(self):
        r = self.register()
        self.assertEqual(r.status_code, 201)
        self.assertEqual(r.get_json()["user"]["email"], "asha@example.com")
        self.assertNotIn("password", str(r.get_json()).lower().replace("password_hash", ""))

    def test_duplicate_email(self):
        self.register()
        r = self.register(email="ASHA@example.com", name="Other Person")
        self.assertEqual(r.status_code, 409)
        self.assertEqual(r.get_json()["field"], "email")

    def test_invalid_inputs(self):
        for over, field in [({"email": "not-an-email"}, "email"), ({"name": "A"}, "name"),
                            ({"password": "short1"}, "password"),
                            ({"password": "onlyletters"}, "password"),
                            ({"password": "12345678"}, "password")]:
            r = self.register(**over)
            self.assertEqual(r.status_code, 400, over)
            self.assertEqual(r.get_json()["field"], field)

    def test_non_json_body(self):
        r = self.c.post("/api/auth/register", data="hello", content_type="text/plain")
        self.assertEqual(r.status_code, 400)

    # database storage
    def test_password_stored_as_hash(self):
        self.register()
        row = self.query("SELECT password_hash FROM users")[0]
        self.assertNotEqual(row[0], GOOD["password"])
        self.assertNotIn(GOOD["password"], row[0])
        self.assertTrue(row[0].startswith(("scrypt:", "pbkdf2:")))

    def test_token_stored_hashed(self):
        self.register()
        token = self.login().get_json()["token"]
        rows = self.query("SELECT token_hash FROM sessions")
        self.assertEqual(len(rows), 1)
        self.assertNotEqual(rows[0][0], token)

    # login / logout
    def test_login_ok(self):
        self.register()
        r = self.login()
        self.assertEqual(r.status_code, 200)
        self.assertIn("token", r.get_json())

    def test_login_wrong_password_and_unknown_email_same_message(self):
        self.register()
        a, b = self.login(password="Wrong1234"), self.login(email="nobody@example.com")
        self.assertEqual((a.status_code, b.status_code), (401, 401))
        self.assertEqual(a.get_json(), b.get_json())

    def test_login_missing_fields(self):
        self.assertEqual(self.c.post("/api/auth/login", json={}).status_code, 400)

    def test_logout_invalidates_token(self):
        h = self.headers()
        self.assertEqual(self.c.get("/api/profile", headers=h).status_code, 200)
        self.assertEqual(self.c.post("/api/auth/logout", headers=h).status_code, 200)
        self.assertEqual(self.c.get("/api/profile", headers=h).status_code, 401)

    def test_protected_routes_need_token(self):
        for method, url in [("get", "/api/profile"), ("get", "/api/detections"),
                            ("post", "/api/detections"), ("post", "/api/auth/logout")]:
            self.assertEqual(getattr(self.c, method)(url).status_code, 401, url)
        bad = {"Authorization": "Bearer " + "x" * 40}
        self.assertEqual(self.c.get("/api/profile", headers=bad).status_code, 401)

    # profile
    def test_profile_update_and_password_change(self):
        h = self.headers()
        r = self.c.put("/api/profile", json={"name": "Asha K Rao"}, headers=h)
        self.assertEqual(r.get_json()["user"]["name"], "Asha K Rao")
        bad = self.c.put("/api/profile", json={"new_password": "NewPass99", "current_password": "nope"}, headers=h)
        self.assertEqual(bad.status_code, 403)
        ok = self.c.put("/api/profile", json={"new_password": "NewPass99", "current_password": GOOD["password"]}, headers=h)
        self.assertEqual(ok.status_code, 200)
        self.assertEqual(self.login().status_code, 401)
        self.assertEqual(self.login(password="NewPass99").status_code, 200)

    # detections
    def test_save_and_list_detection(self):
        h = self.headers()
        r = self.c.post("/api/detections", json=self.det(), headers=h)
        self.assertEqual(r.status_code, 201)
        d = r.get_json()["detection"]
        self.assertEqual(d["crop"], "Tomato")
        self.assertEqual(len(d["record_hash"]), 64)
        self.assertIsNone(d["blockchain_tx"])
        lst = self.c.get("/api/detections", headers=h).get_json()
        self.assertEqual(lst["total"], 1)
        self.assertEqual(self.c.get(f"/api/detections/{d['id']}", headers=h).status_code, 200)

    def test_detection_validation(self):
        h = self.headers()
        for over in [{"crop": "Banana"}, {"disease": ""}, {"confidence": 1.5}, {"confidence": "abc"},
                     {"confidence": -0.1}, {"notes": "x" * 501}]:
            r = self.c.post("/api/detections", json=self.det(**over), headers=h)
            self.assertEqual(r.status_code, 400, over)

    def test_history_is_user_specific(self):
        h1 = self.headers()
        self.c.post("/api/auth/register", json={"name": "Ravi Kumar", "email": "ravi@example.com", "password": "Farm5678"})
        t2 = self.login("ravi@example.com", "Farm5678").get_json()["token"]
        h2 = {"Authorization": f"Bearer {t2}"}
        d = self.c.post("/api/detections", json=self.det(), headers=h1).get_json()["detection"]
        self.assertEqual(self.c.get("/api/detections", headers=h2).get_json()["total"], 0)
        self.assertEqual(self.c.get(f"/api/detections/{d['id']}", headers=h2).status_code, 404)
        self.assertEqual(self.c.delete(f"/api/detections/{d['id']}", headers=h2).status_code, 404)
        self.assertEqual(self.c.delete(f"/api/detections/{d['id']}", headers=h1).status_code, 200)
        self.assertEqual(self.c.get("/api/detections", headers=h1).get_json()["total"], 0)

    def test_pagination(self):
        h = self.headers()
        for i in range(5):
            self.c.post("/api/detections", json=self.det(disease=f"Disease {i}"), headers=h)
        r = self.c.get("/api/detections?per_page=2&page=3", headers=h).get_json()
        self.assertEqual((r["total"], len(r["detections"])), (5, 1))
        self.assertEqual(self.c.get("/api/detections?page=abc", headers=h).status_code, 400)

    # misc
    def test_cors_preflight_and_errors(self):
        r = self.c.options("/api/auth/login", headers={"Origin": "http://localhost:8000",
                           "Access-Control-Request-Method": "POST", "Access-Control-Request-Headers": "content-type,authorization"})
        self.assertEqual(r.headers.get("Access-Control-Allow-Origin"), "http://localhost:8000")
        r = self.c.get("/api/health", headers={"Origin": "http://evil.example"})
        self.assertIsNone(r.headers.get("Access-Control-Allow-Origin"))
        self.assertEqual(self.c.get("/api/nothing").status_code, 404)
        self.assertEqual(self.c.get("/api/auth/login").status_code, 405)
        self.assertIn("error", self.c.get("/api/nothing").get_json())


if __name__ == "__main__":
    unittest.main(verbosity=2)

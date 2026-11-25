import json
import re
import secrets
import hashlib
import sqlite3
import os
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

DB_FILE = "lms.db"
HOST = "127.0.0.1"   # change to "0.0.0.0" to let other devices on your Wi-Fi connect
PORT = 8000
BLOCKED = ("server.py", "lms.db")


def db():
    con = sqlite3.connect(DB_FILE)
    con.row_factory = sqlite3.Row
    return con


def init_db():
    con = db()
    con.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL COLLATE NOCASE,
            salt TEXT NOT NULL,
            password_hash TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )""")
    con.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            token TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )""")
    con.commit()
    con.close()


def hash_password(password, salt_hex):
    return hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), 200000
    ).hex()


class Handler(SimpleHTTPRequestHandler):

    def send_json(self, code, data):
        body = json.dumps(data).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def read_json(self):
        length = int(self.headers.get("Content-Length", 0))
        try:
            return json.loads(self.rfile.read(length) or b"{}")
        except ValueError:
            return {}

    def get_token(self):
        header = self.headers.get("Authorization", "")
        if header.startswith("Bearer "):
            return header[7:]
        return ""

    # ---------- GET ----------
    def do_GET(self):
        name = os.path.basename(self.path.split("?")[0])
        if name in BLOCKED:
            self.send_error(404)
            return

        if self.path == "/api/me":
            con = db()
            row = con.execute(
                "SELECT users.username FROM sessions "
                "JOIN users ON users.id = sessions.user_id "
                "WHERE sessions.token = ?", (self.get_token(),)
            ).fetchone()
            con.close()
            if row:
                self.send_json(200, {"username": row["username"]})
            else:
                self.send_json(401, {"error": "Not logged in"})
            return

        SimpleHTTPRequestHandler.do_GET(self)

    # ---------- POST ----------
    def do_POST(self):
        if self.path == "/api/signup":
            self.signup()
        elif self.path == "/api/login":
            self.login()
        elif self.path == "/api/logout":
            self.logout()
        else:
            self.send_error(404)

    def signup(self):
        data = self.read_json()
        username = str(data.get("username", "")).strip()
        password = str(data.get("password", ""))

        if not re.match(r"^[A-Za-z0-9_]{3,30}$", username):
            self.send_json(400, {"error": "Username must be 3-30 letters, numbers or underscores."})
            return
        if len(password) < 6:
            self.send_json(400, {"error": "Password must be at least 6 characters."})
            return

        salt = secrets.token_hex(16)
        pw_hash = hash_password(password, salt)

        con = db()
        try:
            con.execute(
                "INSERT INTO users (username, salt, password_hash) VALUES (?, ?, ?)",
                (username, salt, pw_hash),
            )
            con.commit()
        except sqlite3.IntegrityError:
            con.close()
            self.send_json(409, {"error": "That username is already taken."})
            return
        con.close()
        self.send_json(201, {"ok": True})

    def login(self):
        data = self.read_json()
        username = str(data.get("username", "")).strip()
        password = str(data.get("password", ""))

        con = db()
        user = con.execute(
            "SELECT * FROM users WHERE username = ?", (username,)
        ).fetchone()

        if not user or not secrets.compare_digest(
            hash_password(password, user["salt"]), user["password_hash"]
        ):
            con.close()
            self.send_json(401, {"error": "Invalid username or password."})
            return

        token = secrets.token_hex(32)
        con.execute(
            "INSERT INTO sessions (token, user_id) VALUES (?, ?)",
            (token, user["id"]),
        )
        con.commit()
        con.close()
        self.send_json(200, {"token": token, "username": user["username"]})

    def logout(self):
        con = db()
        con.execute("DELETE FROM sessions WHERE token = ?", (self.get_token(),))
        con.commit()
        con.close()
        self.send_json(200, {"ok": True})


if __name__ == "__main__":
    init_db()
    print("Running on http://%s:%d" % (HOST, PORT))
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()
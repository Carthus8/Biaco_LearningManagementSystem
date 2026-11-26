import datetime
import hashlib
import json
import mimetypes
import os
import re
import secrets
import shutil
import sqlite3
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import quote, unquote

BASE = os.path.dirname(os.path.abspath(__file__))
DB_FILE = os.path.join(BASE, "lms.db")
UPLOAD_DIR = os.path.join(BASE, "uploads")
HOST = "127.0.0.1"   # "0.0.0.0" lets other devices on your Wi-Fi connect
PORT = 8000
MAX_UPLOAD = 25 * 1024 * 1024  # 25 MB


def db():
    con = sqlite3.connect(DB_FILE, timeout=10)
    con.row_factory = sqlite3.Row
    return con


def init_db():
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    con = db()
    con.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL COLLATE NOCASE,
            salt TEXT NOT NULL,
            password_hash TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            full_name TEXT DEFAULT '',
            email TEXT DEFAULT '',
            bio TEXT DEFAULT '',
            role TEXT DEFAULT 'student'
        );
        CREATE TABLE IF NOT EXISTS sessions (
            token TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS courses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT UNIQUE NOT NULL,
            description TEXT DEFAULT ''
        );
        CREATE TABLE IF NOT EXISTS activities (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            course_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            description TEXT DEFAULT '',
            due_date TEXT DEFAULT '',
            created_by INTEGER,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            activity_id INTEGER NOT NULL,
            original_name TEXT NOT NULL,
            stored_name TEXT NOT NULL,
            size INTEGER DEFAULT 0,
            uploaded_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS completions (
            user_id INTEGER NOT NULL,
            activity_id INTEGER NOT NULL,
            PRIMARY KEY (user_id, activity_id)
        );
    """)
    # Upgrade an older users table that lacks the profile columns
    cols = [r["name"] for r in con.execute("PRAGMA table_info(users)")]
    for name, ddl in (("full_name", "TEXT DEFAULT ''"), ("email", "TEXT DEFAULT ''"),
                      ("bio", "TEXT DEFAULT ''"), ("role", "TEXT DEFAULT 'student'")):
        if name not in cols:
            con.execute("ALTER TABLE users ADD COLUMN %s %s" % (name, ddl))
    # If nobody is a teacher yet, the oldest account becomes the teacher
    if not con.execute("SELECT 1 FROM users WHERE role = 'teacher'").fetchone():
        con.execute("UPDATE users SET role = 'teacher' WHERE id = (SELECT MIN(id) FROM users)")
    con.execute("INSERT OR IGNORE INTO courses (title, description) VALUES (?, ?)",
                ("Systems Integration",
                 "Activities, files and announcements for Systems Integration."))
    con.commit()
    con.close()


def hash_password(password, salt_hex):
    return hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), 200000
    ).hex()


def user_json(u):
    return {
        "username": u["username"],
        "full_name": u["full_name"] or "",
        "email": u["email"] or "",
        "bio": u["bio"] or "",
        "role": u["role"] or "student",
        "created_at": u["created_at"],
    }


def valid_date(s):
    if s == "":
        return True
    try:
        datetime.date.fromisoformat(s)
        return len(s) == 10
    except ValueError:
        return False


class Handler(SimpleHTTPRequestHandler):

    # ---------- plumbing ----------
    def handle(self):
        try:
            SimpleHTTPRequestHandler.handle(self)
        except (BrokenPipeError, ConnectionResetError):
            pass  # browser disconnected early

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        SimpleHTTPRequestHandler.end_headers(self)

    def send_json(self, code, data):
        body = json.dumps(data).encode("utf-8")
        try:
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def read_json(self):
        try:
            length = int(self.headers.get("Content-Length", 0))
            raw = self.rfile.read(length) if length > 0 else b""
            data = json.loads(raw or b"{}")
            return data if isinstance(data, dict) else {}
        except (ValueError, TypeError):
            return {}

    def drain(self):
        """Read and discard an unused request body so the browser gets our reply."""
        try:
            remaining = min(int(self.headers.get("Content-Length", 0)), MAX_UPLOAD)
        except ValueError:
            return
        while remaining > 0:
            chunk = self.rfile.read(min(65536, remaining))
            if not chunk:
                break
            remaining -= len(chunk)

    def get_token(self):
        header = self.headers.get("Authorization", "")
        return header[7:] if header.startswith("Bearer ") else ""

    def current_user(self):
        token = self.get_token()
        if not token:
            return None
        con = db()
        row = con.execute(
            "SELECT users.* FROM sessions JOIN users ON users.id = sessions.user_id "
            "WHERE sessions.token = ?", (token,)
        ).fetchone()
        con.close()
        return row

    def require_teacher(self, user):
        if user["role"] != "teacher":
            self.drain()
            self.send_json(403, {"error": "Only the teacher can do that."})
            return False
        return True

    def is_blocked(self, path):
        low = unquote(path).lower()
        parts = [p for p in low.split("/") if p]
        if any(p.startswith(".") for p in parts):
            return True
        if parts and parts[0] == "uploads":
            return True
        return low.endswith((".db", ".py"))

    # ---------- HTTP verbs ----------
    def do_GET(self):
        path = self.path.split("?")[0]
        if path.startswith("/api/"):
            return self.api("GET", path)
        if self.is_blocked(path):
            return self.send_error(404)
        SimpleHTTPRequestHandler.do_GET(self)

    def do_POST(self):
        self.api("POST", self.path.split("?")[0])

    def do_DELETE(self):
        self.api("DELETE", self.path.split("?")[0])

    def api(self, method, path):
        try:
            self.route(method, path)
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception as e:
            print("Server error:", repr(e))
            self.send_json(500, {"error": "Server error."})

    # ---------- router ----------
    def route(self, method, path):
        if method == "POST" and path == "/api/signup":
            return self.signup()
        if method == "POST" and path == "/api/login":
            return self.login()

        user = self.current_user()
        if not user:
            self.drain()
            return self.send_json(401, {"error": "Not logged in"})

        if method == "POST" and path == "/api/logout":
            return self.logout()
        if method == "GET" and path == "/api/me":
            return self.send_json(200, user_json(user))
        if method == "POST" and path == "/api/profile":
            return self.update_profile(user)
        if method == "GET" and path == "/api/courses":
            return self.list_courses()
        if method == "GET" and path == "/api/todos":
            return self.todos(user)

        m = re.match(r"^/api/courses/(\d+)/activities$", path)
        if m and method == "GET":
            return self.list_activities(user, int(m.group(1)))
        if m and method == "POST":
            return self.create_activity(user, int(m.group(1)))

        m = re.match(r"^/api/activities/(\d+)$", path)
        if m and method == "DELETE":
            return self.delete_activity(user, int(m.group(1)))

        m = re.match(r"^/api/activities/(\d+)/files$", path)
        if m and method == "POST":
            return self.upload_file(user, int(m.group(1)))

        m = re.match(r"^/api/activities/(\d+)/done$", path)
        if m and method == "POST":
            return self.set_done(user, int(m.group(1)))

        m = re.match(r"^/api/files/(\d+)$", path)
        if m and method == "GET":
            return self.download_file(int(m.group(1)))
        if m and method == "DELETE":
            return self.delete_file(user, int(m.group(1)))

        self.drain()
        self.send_json(404, {"error": "Not found"})

    # ---------- accounts ----------
    def signup(self):
        data = self.read_json()
        username = str(data.get("username", "")).strip()
        password = str(data.get("password", ""))
        if not re.match(r"^[A-Za-z0-9_]{3,30}$", username):
            return self.send_json(400, {"error": "Username must be 3-30 letters, numbers or underscores."})
        if len(password) < 6:
            return self.send_json(400, {"error": "Password must be at least 6 characters."})

        salt = secrets.token_hex(16)
        pw_hash = hash_password(password, salt)
        con = db()
        first = con.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0
        try:
            con.execute(
                "INSERT INTO users (username, salt, password_hash, role) VALUES (?, ?, ?, ?)",
                (username, salt, pw_hash, "teacher" if first else "student"))
            con.commit()
        except sqlite3.IntegrityError:
            con.close()
            return self.send_json(409, {"error": "That username is already taken."})
        con.close()
        self.send_json(201, {"ok": True})

    def login(self):
        data = self.read_json()
        username = str(data.get("username", "")).strip()
        password = str(data.get("password", ""))
        con = db()
        user = con.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
        if not user or not secrets.compare_digest(
                hash_password(password, user["salt"]), user["password_hash"]):
            con.close()
            return self.send_json(401, {"error": "Invalid username or password."})
        token = secrets.token_hex(32)
        con.execute("INSERT INTO sessions (token, user_id) VALUES (?, ?)", (token, user["id"]))
        con.commit()
        con.close()
        self.send_json(200, {"token": token, "username": user["username"]})

    def logout(self):
        con = db()
        con.execute("DELETE FROM sessions WHERE token = ?", (self.get_token(),))
        con.commit()
        con.close()
        self.send_json(200, {"ok": True})

    def update_profile(self, user):
        data = self.read_json()
        full_name = str(data.get("full_name", "")).strip()
        email = str(data.get("email", "")).strip()
        bio = str(data.get("bio", "")).strip()
        if len(full_name) > 60 or len(bio) > 300 or len(email) > 100:
            return self.send_json(400, {"error": "One of the fields is too long."})
        if email and "@" not in email:
            return self.send_json(400, {"error": "Please enter a valid email."})
        con = db()
        con.execute("UPDATE users SET full_name = ?, email = ?, bio = ? WHERE id = ?",
                    (full_name, email, bio, user["id"]))
        con.commit()
        row = con.execute("SELECT * FROM users WHERE id = ?", (user["id"],)).fetchone()
        con.close()
        self.send_json(200, user_json(row))

    # ---------- courses and activities ----------
    def list_courses(self):
        con = db()
        rows = con.execute(
            "SELECT c.id, c.title, c.description, "
            "(SELECT COUNT(*) FROM activities a WHERE a.course_id = c.id) AS activity_count "
            "FROM courses c ORDER BY c.id").fetchall()
        con.close()
        self.send_json(200, {"courses": [dict(r) for r in rows]})

    def list_activities(self, user, cid):
        con = db()
        course = con.execute("SELECT * FROM courses WHERE id = ?", (cid,)).fetchone()
        if not course:
            con.close()
            return self.send_json(404, {"error": "Course not found."})
        acts = con.execute(
            "SELECT a.*, EXISTS(SELECT 1 FROM completions c WHERE c.activity_id = a.id "
            "AND c.user_id = ?) AS done FROM activities a WHERE a.course_id = ? "
            "ORDER BY (a.due_date = ''), a.due_date, a.id", (user["id"], cid)).fetchall()
        result = []
        for a in acts:
            files = con.execute(
                "SELECT id, original_name, size FROM files WHERE activity_id = ? ORDER BY id",
                (a["id"],)).fetchall()
            result.append({
                "id": a["id"], "title": a["title"], "description": a["description"],
                "due_date": a["due_date"], "done": bool(a["done"]),
                "created_at": a["created_at"],
                "files": [{"id": f["id"], "name": f["original_name"], "size": f["size"]} for f in files],
            })
        con.close()
        self.send_json(200, {
            "course": {"id": course["id"], "title": course["title"], "description": course["description"]},
            "activities": result})

    def create_activity(self, user, cid):
        if not self.require_teacher(user):
            return
        data = self.read_json()
        title = str(data.get("title", "")).strip()
        description = str(data.get("description", "")).strip()
        due = str(data.get("due_date", "")).strip()
        if not title or len(title) > 120:
            return self.send_json(400, {"error": "Title is required (max 120 characters)."})
        if len(description) > 5000:
            return self.send_json(400, {"error": "Description is too long."})
        if not valid_date(due):
            return self.send_json(400, {"error": "Invalid due date."})
        con = db()
        if not con.execute("SELECT 1 FROM courses WHERE id = ?", (cid,)).fetchone():
            con.close()
            return self.send_json(404, {"error": "Course not found."})
        cur = con.execute(
            "INSERT INTO activities (course_id, title, description, due_date, created_by) "
            "VALUES (?, ?, ?, ?, ?)", (cid, title, description, due, user["id"]))
        con.commit()
        new_id = cur.lastrowid
        con.close()
        self.send_json(201, {"id": new_id})

    def delete_activity(self, user, aid):
        if not self.require_teacher(user):
            return
        con = db()
        files = con.execute("SELECT stored_name FROM files WHERE activity_id = ?", (aid,)).fetchall()
        con.execute("DELETE FROM files WHERE activity_id = ?", (aid,))
        con.execute("DELETE FROM completions WHERE activity_id = ?", (aid,))
        con.execute("DELETE FROM activities WHERE id = ?", (aid,))
        con.commit()
        con.close()
        for f in files:
            try:
                os.remove(os.path.join(UPLOAD_DIR, f["stored_name"]))
            except OSError:
                pass
        self.send_json(200, {"ok": True})

    def set_done(self, user, aid):
        data = self.read_json()
        con = db()
        if not con.execute("SELECT 1 FROM activities WHERE id = ?", (aid,)).fetchone():
            con.close()
            return self.send_json(404, {"error": "Activity not found."})
        if data.get("done"):
            con.execute("INSERT OR IGNORE INTO completions (user_id, activity_id) VALUES (?, ?)",
                        (user["id"], aid))
        else:
            con.execute("DELETE FROM completions WHERE user_id = ? AND activity_id = ?",
                        (user["id"], aid))
        con.commit()
        con.close()
        self.send_json(200, {"ok": True})

    def todos(self, user):
        con = db()
        rows = con.execute(
            "SELECT a.id, a.title, a.due_date, a.course_id, c.title AS course_title "
            "FROM activities a JOIN courses c ON c.id = a.course_id "
            "WHERE a.due_date <> '' AND NOT EXISTS (SELECT 1 FROM completions x "
            "WHERE x.activity_id = a.id AND x.user_id = ?) "
            "ORDER BY a.due_date, a.id LIMIT 15", (user["id"],)).fetchall()
        con.close()
        self.send_json(200, {"todos": [dict(r) for r in rows]})

    # ---------- files ----------
    def upload_file(self, user, aid):
        if not self.require_teacher(user):
            return
        con = db()
        exists = con.execute("SELECT 1 FROM activities WHERE id = ?", (aid,)).fetchone()
        if not exists:
            con.close()
            self.drain()
            return self.send_json(404, {"error": "Activity not found."})
        try:
            length = int(self.headers.get("Content-Length", 0))
        except ValueError:
            length = 0
        if length <= 0:
            con.close()
            return self.send_json(400, {"error": "Empty file."})
        if length > MAX_UPLOAD:
            con.close()
            return self.send_json(413, {"error": "File is larger than 25 MB."})

        name = unquote(self.headers.get("X-Filename", "file")).replace("\\", "/")
        name = os.path.basename(name).strip()[:200] or "file"
        stored = secrets.token_hex(16)
        path = os.path.join(UPLOAD_DIR, stored)

        remaining = length
        with open(path, "wb") as out:
            while remaining > 0:
                chunk = self.rfile.read(min(65536, remaining))
                if not chunk:
                    break
                out.write(chunk)
                remaining -= len(chunk)
        if remaining > 0:
            os.remove(path)
            con.close()
            return self.send_json(400, {"error": "Upload was interrupted."})

        cur = con.execute(
            "INSERT INTO files (activity_id, original_name, stored_name, size) VALUES (?, ?, ?, ?)",
            (aid, name, stored, length))
        con.commit()
        new_id = cur.lastrowid
        con.close()
        self.send_json(201, {"id": new_id, "name": name, "size": length})

    def download_file(self, fid):
        con = db()
        row = con.execute("SELECT * FROM files WHERE id = ?", (fid,)).fetchone()
        con.close()
        path = os.path.join(UPLOAD_DIR, row["stored_name"]) if row else ""
        if not row or not os.path.isfile(path):
            return self.send_json(404, {"error": "File not found."})
        ctype = mimetypes.guess_type(row["original_name"])[0] or "application/octet-stream"
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(os.path.getsize(path)))
        self.send_header("Content-Disposition",
                         "attachment; filename*=UTF-8''" + quote(row["original_name"]))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        with open(path, "rb") as f:
            shutil.copyfileobj(f, self.wfile)

    def delete_file(self, user, fid):
        if not self.require_teacher(user):
            return
        con = db()
        row = con.execute("SELECT stored_name FROM files WHERE id = ?", (fid,)).fetchone()
        con.execute("DELETE FROM files WHERE id = ?", (fid,))
        con.commit()
        con.close()
        if row:
            try:
                os.remove(os.path.join(UPLOAD_DIR, row["stored_name"]))
            except OSError:
                pass
        self.send_json(200, {"ok": True})


if __name__ == "__main__":
    os.chdir(BASE)   # always serve the folder this file lives in
    init_db()
    print("Running on http://%s:%d" % (HOST, PORT))
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()
import hashlib
import hmac
import json
import secrets
import socket
import sqlite3
import threading
import time
from pathlib import Path

HOST = "0.0.0.0"
PORT = [port]
DB_FILE = Path(__file__).with_name("db.db")

clients = {}  # username -> {"socket": socket, "send_lock": Lock}
clients_lock = threading.Lock()
db_lock = threading.Lock()
stop_event = threading.Event()


def get_db():
    conn = sqlite3.connect(DB_FILE, timeout=15)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    # This creates db.db automatically if it doesn't exist.
    with get_db() as db:
        db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                username TEXT PRIMARY KEY COLLATE NOCASE,
                password_salt TEXT NOT NULL,
                password_hash TEXT NOT NULL,
                created_at REAL NOT NULL
            )
        """)
        db.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                token_hash TEXT PRIMARY KEY,
                username TEXT NOT NULL COLLATE NOCASE,
                created_at REAL NOT NULL,
                FOREIGN KEY(username) REFERENCES users(username) ON DELETE CASCADE
            )
        """)
        db.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sender TEXT NOT NULL,
                recipient TEXT,
                body TEXT NOT NULL,
                created_at REAL NOT NULL
            )
        """)
        db.execute("CREATE INDEX IF NOT EXISTS idx_messages_created ON messages(created_at)")
        db.execute("CREATE INDEX IF NOT EXISTS idx_messages_recipient ON messages(recipient)")


def hash_password(password, salt=None):
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, 250_000
    )
    return salt.hex(), digest.hex()


def send_json(sock, lock, payload):
    data = (json.dumps(payload, ensure_ascii=False) + "\n").encode("utf-8")
    with lock:
        sock.sendall(data)


def recv_json_file(sock):
    """Read newline-delimited JSON messages, one at a time."""
    buffer = b""
    while True:
        chunk = sock.recv(4096)
        if not chunk:
            return
        buffer += chunk
        while b"\n" in buffer:
            line, buffer = buffer.split(b"\n", 1)
            if not line.strip():
                continue
            try:
                yield json.loads(line.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                yield {"type": "_invalid"}


def token_digest(token):
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_account(username, password):
    salt, digest = hash_password(password)
    try:
        with db_lock, get_db() as db:
            db.execute(
                "INSERT INTO users(username, password_salt, password_hash, created_at) VALUES (?, ?, ?, ?)",
                (username, salt, digest, time.time()),
            )
        return True, "Account created."
    except sqlite3.IntegrityError:
        return False, "That username is already taken."
    except sqlite3.Error as exc:
        return False, f"Database error: {exc}"


def verify_password(username, password):
    with db_lock, get_db() as db:
        row = db.execute(
            "SELECT password_salt, password_hash FROM users WHERE username = ? COLLATE NOCASE",
            (username,),
        ).fetchone()
    if row is None:
        return None
    salt = bytes.fromhex(row["password_salt"])
    actual = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, 250_000
    ).hex()
    if hmac.compare_digest(actual, row["password_hash"]):
        return username
    return None


def create_session(username):
    token = secrets.token_urlsafe(32)
    with db_lock, get_db() as db:
        db.execute(
            "INSERT INTO sessions(token_hash, username, created_at) VALUES (?, ?, ?)",
            (token_digest(token), username, time.time()),
        )
    return token


def authenticate_token(token):
    if not isinstance(token, str) or len(token) > 256:
        return None
    with db_lock, get_db() as db:
        row = db.execute(
            """SELECT users.username
               FROM sessions JOIN users ON users.username = sessions.username
               WHERE sessions.token_hash = ?""",
            (token_digest(token),),
        ).fetchone()
    return row["username"] if row else None


def revoke_session(token):
    if not isinstance(token, str):
        return
    with db_lock, get_db() as db:
        db.execute("DELETE FROM sessions WHERE token_hash = ?", (token_digest(token),))


def save_message(sender, recipient, body):
    with db_lock, get_db() as db:
        db.execute(
            "INSERT INTO messages(sender, recipient, body, created_at) VALUES (?, ?, ?, ?)",
            (sender, recipient, body, time.time()),
        )


def username_exists(username):
    with db_lock, get_db() as db:
        return db.execute(
            "SELECT 1 FROM users WHERE username = ? COLLATE NOCASE", (username,)
        ).fetchone() is not None


def deliver_online(username, payload):
    with clients_lock:
        entry = clients.get(username.casefold())
    if not entry:
        return False
    try:
        send_json(entry["socket"], entry["send_lock"], payload)
        return True
    except OSError:
        return False


def broadcast(payload, exclude=None):
    with clients_lock:
        targets = [
            (name, entry) for name, entry in clients.items()
            if name != (exclude.casefold() if exclude else None)
        ]
    for name, entry in targets:
        try:
            send_json(entry["socket"], entry["send_lock"], payload)
        except OSError:
            # The receiver thread will clean up the connection.
            pass


def online_user(username, sock, send_lock):
    key = username.casefold()
    with clients_lock:
        # A single account can only have one active connection in this prototype.
        old = clients.get(key)
        clients[key] = {"username": username, "socket": sock, "send_lock": send_lock}
    if old and old["socket"] is not sock:
        try:
            send_json(old["socket"], old["send_lock"], {
                "type": "notice",
                "text": "This account was signed in from another connection."
            })
            old["socket"].shutdown(socket.SHUT_RDWR)
            old["socket"].close()
        except OSError:
            pass
    broadcast({"type": "notice", "text": f"{username} Joined to chat."}, exclude=username)


def offline_user(username, sock):
    if not username:
        return
    key = username.casefold()
    removed = False
    with clients_lock:
        entry = clients.get(key)
        if entry and entry["socket"] is sock:
            del clients[key]
            removed = True
    if removed:
        broadcast({"type": "notice", "text": f"{username} Left the chat."})


def valid_username(username):
    if not isinstance(username, str) or not (3 <= len(username) <= 20):
        return False
    return all(ch.isalnum() or ch == "_" for ch in username)


def handle_client(sock, address):
    username = None
    session_token = None
    send_lock = threading.Lock()
    try:
        sock.settimeout(None)
        send_json(sock, send_lock, {
            "type": "hello",
            "message": "Welcome! Use new <name> <pass> <pass> or login <name> <pass>."
        })

        for request in recv_json_file(sock):
            if request.get("type") == "_invalid":
                send_json(sock, send_lock, {"type": "error", "message": "Invalid JSON request."})
                continue

            action = request.get("action")

            if action == "register":
                if username:
                    send_json(sock, send_lock, {"type": "error", "message": "You are already logged in."})
                    continue
                name = request.get("username", "")
                password = request.get("password", "")
                if not valid_username(name):
                    send_json(sock, send_lock, {
                        "type": "error",
                        "message": "Username must be 3-20 characters: letters, numbers, or underscore."
                    })
                    continue
                if not isinstance(password, str) or not (4 <= len(password) <= 128):
                    send_json(sock, send_lock, {"type": "error", "message": "Password must be 4-128 characters."})
                    continue
                ok, message = create_account(name, password)
                if not ok:
                    send_json(sock, send_lock, {"type": "error", "message": message})
                    continue
                username = name
                session_token = create_session(username)
                online_user(username, sock, send_lock)
                send_json(sock, send_lock, {
                    "type": "auth_ok", "username": username,
                    "token": session_token, "message": "Account created and logged in."
                })

            elif action == "login":
                if username:
                    send_json(sock, send_lock, {"type": "error", "message": "You are already logged in."})
                    continue
                name = request.get("username", "")
                password = request.get("password", "")
                if not isinstance(name, str) or not isinstance(password, str):
                    send_json(sock, send_lock, {"type": "error", "message": "Invalid credentials."})
                    continue
                verified_name = verify_password(name, password)
                if not verified_name:
                    send_json(sock, send_lock, {"type": "error", "message": "Wrong username or password."})
                    continue
                username = verified_name
                session_token = create_session(username)
                online_user(username, sock, send_lock)
                send_json(sock, send_lock, {
                    "type": "auth_ok", "username": username,
                    "token": session_token, "message": "Logged in."
                })

            elif action == "resume":
                if username:
                    send_json(sock, send_lock, {"type": "error", "message": "Already logged in."})
                    continue
                token = request.get("token", "")
                resumed_name = authenticate_token(token)
                if not resumed_name:
                    send_json(sock, send_lock, {"type": "resume_failed", "message": "Saved session is invalid. Please log in."})
                    continue
                username = resumed_name
                session_token = token
                online_user(username, sock, send_lock)
                send_json(sock, send_lock, {
                    "type": "auth_ok", "username": username,
                    "token": session_token, "message": "Session restored."
                })

            elif action == "chat":
                if not username:
                    send_json(sock, send_lock, {"type": "error", "message": "Log in first."})
                    continue
                recipient = request.get("recipient")
                body = request.get("message")
                if not isinstance(body, str) or not body.strip() or len(body) > 2000:
                    send_json(sock, send_lock, {"type": "error", "message": "Message must be 1-2000 characters."})
                    continue
                body = body.strip()
                if recipient is None:
                    save_message(username, None, body)
                    broadcast({"type": "chat", "sender": username, "message": body})
                else:
                    if not isinstance(recipient, str) or not username_exists(recipient):
                        send_json(sock, send_lock, {"type": "error", "message": "That user does not exist."})
                        continue
                    if recipient.casefold() == username.casefold():
                        send_json(sock, send_lock, {"type": "error", "message": "You cannot send a private message to yourself."})
                        continue
                    save_message(username, recipient, body)
                    delivered = deliver_online(recipient, {
                        "type": "private", "sender": username, "message": body
                    })
                    if delivered:
                        send_json(sock, send_lock, {
                            "type": "sent", "message": f"Private message sent to {recipient}."
                        })
                    else:
                        send_json(sock, send_lock, {
                            "type": "error", "message": f"{recipient} is offline; message was not delivered."
                        })

            elif action == "logout":
                if username:
                    old_name = username
                    old_token = session_token
                    offline_user(old_name, sock)
                    if old_token:
                        revoke_session(old_token)
                    username = None
                    session_token = None
                    send_json(sock, send_lock, {"type": "logged_out", "message": "Logged out."})
                else:
                    send_json(sock, send_lock, {"type": "logged_out", "message": "You are not logged in."})

            elif action == "quit":
                break
            else:
                send_json(sock, send_lock, {"type": "error", "message": "Unknown action."})

    except (ConnectionError, OSError):
        pass
    except Exception as exc:
        print(f"[ERROR] Client {address}: {exc}")
        try:
            send_json(sock, send_lock, {"type": "error", "message": "Internal server error."})
        except OSError:
            pass
    finally:
        offline_user(username, sock)
        try:
            sock.close()
        except OSError:
            pass


def main():
    init_db()
    print(f"[SERVER] Database ready: {DB_FILE}")
    print(f"[SERVER] Listening on {HOST}:{PORT}")
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind((HOST, PORT))
        server.listen()
        try:
            while True:
                conn, address = server.accept()
                print(f"[CONNECT] {address}")
                threading.Thread(
                    target=handle_client, args=(conn, address), daemon=True
                ).start()
        except KeyboardInterrupt:
            print("\n[SERVER] Shutting down...")
        finally:
            stop_event.set()


if __name__ == "__main__":
    main()

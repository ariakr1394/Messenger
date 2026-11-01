import json
import socket
import threading
from pathlib import Path
import os

SERVER_HOST = "[ip]"
SERVER_PORT = [port]

APPDATA = Path(os.getenv("APPDATA", Path.home()))
APP_FOLDER = APPDATA / "Messenger"

APP_FOLDER.mkdir(parents=True, exist_ok=True)

SESSION_FILE = APP_FOLDER / "session.json"

sock = None
send_lock = threading.Lock()

current_username = None
current_token = None

logged_in = threading.Event()
auth_response = threading.Event()
stop_reader = threading.Event()


# -------------------------
# Network
# -------------------------

def send_request(payload):
    data = (
        json.dumps(payload, ensure_ascii=False) + "\n"
    ).encode("utf-8")

    with send_lock:
        sock.sendall(data)


def read_messages():
    global current_username, current_token

    buffer = b""

    try:
        while not stop_reader.is_set():
            chunk = sock.recv(4096)

            if not chunk:
                print("\n[INFO] Disconnected from server.")
                break

            buffer += chunk

            while b"\n" in buffer:
                line, buffer = buffer.split(b"\n", 1)

                if not line.strip():
                    continue

                try:
                    message = json.loads(line.decode("utf-8"))
                    handle_server_message(message)

                except (UnicodeDecodeError, json.JSONDecodeError):
                    print("\n[WARN] Invalid server response.")

    except OSError:
        pass

    finally:
        stop_reader.set()
        logged_in.clear()


# -------------------------
# Server messages
# -------------------------

def handle_server_message(message):
    global current_username, current_token

    kind = message.get("type")

    if kind == "hello":
        print(f"\n{message.get('message', '')}")

    elif kind == "auth_ok":
        current_username = message.get("username")
        current_token = message.get("token")

        save_session(current_username, current_token)

        logged_in.set()
        auth_response.set()

        print(f"\n[SUCCESS] {message.get('message', 'Logged in.')}")
        print(f"Welcome, {current_username}!")

        print("Public: . message")
        print("Private: name message")
        print("Logout: exit")

    elif kind == "resume_failed":
        auth_response.set()
        clear_session()

        print("\n[INFO] Saved session is invalid.")

    elif kind == "chat":
        print(f"\n{message.get('sender')}: {message.get('message')}")
        show_prompt()

    elif kind == "private":
        print(
            f"\n[Private] {message.get('sender')}: "
            f"{message.get('message')}"
        )
        show_prompt()

    elif kind == "notice":
        print(f"\n{message.get('text', '')}")
        show_prompt()

    elif kind == "sent":
        print(f"\n{message.get('message', '')}")
        show_prompt()

    elif kind == "logged_out":
        current_username = None
        current_token = None

        clear_session()
        logged_in.clear()

        print(f"\n{message.get('message', 'Logged out.')}")

    elif kind == "error":
        auth_response.set()
        print(f"\n[ERROR] {message.get('message', 'Unknown error.')}")
        show_prompt()


def show_prompt():
    if logged_in.is_set():
        print("> ", end="", flush=True)


# -------------------------
# Session management
# -------------------------

def save_session(username, token):
    if not username or not token:
        return

    try:
        SESSION_FILE.write_text(
            json.dumps({
                "username": username,
                "token": token
            }),
            encoding="utf-8"
        )

    except OSError as exc:
        print(f"[WARN] Cannot save session: {exc}")
        
def load_session():
    try:
        data = json.loads(
            SESSION_FILE.read_text(encoding="utf-8")
        )

        if isinstance(data, dict):
            username = data.get("username")
            token = data.get("token")

            if isinstance(username, str) and isinstance(token, str):
                return username, token

    except (OSError, json.JSONDecodeError):
        pass

    return None, None


def clear_session():
    try:
        SESSION_FILE.unlink(missing_ok=True)

    except OSError as exc:
        print(f"[WARN] Cannot remove session: {exc}")

# -------------------------
# Connection
# -------------------------

def connect():
    global sock

    sock = socket.create_connection(
        (SERVER_HOST, SERVER_PORT),
        timeout=10
    )

    sock.settimeout(None)

    threading.Thread(
        target=read_messages,
        daemon=True
    ).start()


def wait_for_auth_response(timeout=15):
    got_response = auth_response.wait(timeout)
    auth_response.clear()

    return got_response


# -------------------------
# Chat commands
# -------------------------

def parse_chat_command(line):

    stripped = line.strip()

    if not stripped:
        return

    if stripped.lower() == "exit":
        send_request({"action": "logout"})
        return

    # Public message
    if stripped.startswith("."):
        body = stripped[1:].strip()

        if body:
            send_request({
                "action": "chat",
                "recipient": None,
                "message": body
            })
        else:
            print("Usage: . message")

        return

    # Private message
    parts = stripped.split(maxsplit=1)

    if len(parts) < 2:
        print("Usage: name message | . public message | exit")
        return

    recipient, body = parts

    send_request({
        "action": "chat",
        "recipient": recipient,
        "message": body
    })


# -------------------------
# Main
# -------------------------

def main():

    try:
        connect()

    except OSError as exc:
        print(f"[ERROR] Cannot connect: {exc}")
        print("Start Server.py first.")
        return

    saved_username, saved_token = load_session()

    # Automatic login
    if saved_token:

        print(
            f"[INFO] Restoring session for {saved_username}..."
        )

        auth_response.clear()

        send_request({
            "action": "resume",
            "token": saved_token
        })

        wait_for_auth_response()

    while not stop_reader.is_set():

        if logged_in.is_set():

            try:
                line = input("> ")

            except (EOFError, KeyboardInterrupt):
                print()

                send_request({"action": "logout"})
                break

            try:
                parse_chat_command(line)

            except OSError:
                print("[ERROR] Connection lost.")
                break

            continue

        try:
            line = input(
                "Not logged in "
                "(login name pass | new name pass pass | quit): "
            ).strip()

        except (EOFError, KeyboardInterrupt):
            print()
            break

        if not line:
            continue

        parts = line.split()

        if parts[0].lower() == "quit":
            send_request({"action": "quit"})
            break

        elif parts[0].lower() == "new":

            if len(parts) != 4:
                print("Usage: new name pass pass")
                continue

            _, username, password1, password2 = parts

            if password1 != password2:
                print("Passwords do not match.")
                continue

            auth_response.clear()

            send_request({
                "action": "register",
                "username": username,
                "password": password1
            })

            wait_for_auth_response()

        elif parts[0].lower() == "login":

            if len(parts) != 3:
                print("Usage: login name pass")
                continue

            _, username, password = parts

            auth_response.clear()

            send_request({
                "action": "login",
                "username": username,
                "password": password
            })

            wait_for_auth_response()

        else:
            print(
                "Unknown command. "
                "Use: login name pass | new name pass pass | quit"
            )

    stop_reader.set()

    try:
        sock.shutdown(socket.SHUT_RDWR)
        sock.close()

    except OSError:
        pass


if __name__ == "__main__":
    main()

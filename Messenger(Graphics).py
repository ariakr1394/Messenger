import json
import socket
import threading
from pathlib import Path
import os
import tkinter as tk
from tkinter import messagebox

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

connected = threading.Event()
logged_in = threading.Event()
auth_response = threading.Event()
stop_reader = threading.Event()

status_label = None

root = tk.Tk()
root.title("Messenger")
root.geometry("1000x700")
root.minsize(650, 450)
root.configure(bg="#10131c")

# Colors
BG = "#10131c"
PANEL = "#191e2b"
INPUT = "#252c3b"
ACCENT = "#6366f1"
TEXT = "#f1f5f9"
MUTED = "#94a3b8"
GREEN = "#22c55e"
RED = "#ef4444"

FONT = ("Segoe UI", 10)


# -------------------------
# UI Helpers
# -------------------------

def clear_window():
    for widget in root.winfo_children():
        widget.destroy()


def add_message(sender, message, private=False, system=False):

    if system:
        tag = "system"
    elif private:
        tag = "private"
    elif sender == current_username:
        tag = "me"
    else:
        tag = "other"

    chat_box.configure(state="normal")

    chat_box.insert("end", f"{sender}: ", tag)
    chat_box.insert("end", f"{message}\n\n", tag)

    chat_box.configure(state="disabled")
    chat_box.see("end")


def set_status(text, color=MUTED):
    global status_label

    if status_label is None:
        return

    try:
        if status_label.winfo_exists():
            status_label.config(text=text, fg=color)
    except (tk.TclError, AttributeError):
        pass


def ui(callback, *args):
    try:
        root.after(0, lambda: callback(*args))
    except (RuntimeError, tk.TclError):
        pass


# -------------------------
# Session
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
    except OSError:
        pass


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
    except OSError:
        pass


# -------------------------
# Network
# -------------------------

def send_request(payload):

    if not connected.is_set() or sock is None:
        raise OSError("Not connected")

    data = (
        json.dumps(payload, ensure_ascii=False) + "\n"
    ).encode("utf-8")

    with send_lock:
        sock.sendall(data)


def connect():

    global sock

    sock = socket.create_connection(
        (SERVER_HOST, SERVER_PORT),
        timeout=10
    )

    sock.settimeout(None)
    connected.set()

    threading.Thread(
        target=read_messages,
        daemon=True
    ).start()


def read_messages():

    buffer = b""

    try:
        while not stop_reader.is_set():

            chunk = sock.recv(4096)

            if not chunk:
                break

            buffer += chunk

            while b"\n" in buffer:

                line, buffer = buffer.split(b"\n", 1)

                if not line.strip():
                    continue

                try:
                    message = json.loads(
                        line.decode("utf-8")
                    )

                    handle_server_message(message)

                except (UnicodeDecodeError, json.JSONDecodeError):
                    pass

    except OSError:
        pass

    finally:
        connected.clear()
        logged_in.clear()
        stop_reader.set()

        ui(set_status, "Disconnected", RED)

        if root.winfo_exists():
            ui(show_login, "Connection lost. Please restart the client.")


# -------------------------
# Server Messages
# -------------------------

def handle_server_message(message):

    global current_username, current_token

    kind = message.get("type")

    if kind == "hello":

        ui(set_status, "Connected", GREEN)

    elif kind == "auth_ok":

        current_username = message.get("username")
        current_token = message.get("token")

        save_session(current_username, current_token)

        logged_in.set()
        auth_response.set()

        ui(show_chat)

    elif kind == "resume_failed":

        clear_session()
        auth_response.set()

        ui(show_login, "Saved session is invalid.")

    elif kind == "chat":

        ui(
            add_message,
            message.get("sender", "Unknown"),
            message.get("message", "")
        )

    elif kind == "private":

        ui(
            add_message,
            message.get("sender", "Unknown"),
            message.get("message", ""),
            True
        )

    elif kind == "notice":

        ui(
            add_message,
            "SERVER",
            message.get("text", ""),
            False,
            True
        )

    elif kind == "sent":

        ui(
            add_message,
            "SYSTEM",
            message.get("message", ""),
            False,
            True
        )

    elif kind == "logged_out":

        current_username = None
        current_token = None

        clear_session()
        logged_in.clear()

        ui(show_login, "Logged out successfully.")

    elif kind == "error":

        auth_response.set()

        ui(
            messagebox.showerror,
            "Messenger Error",
            message.get("message", "Unknown error.")
        )


# -------------------------
# Login Screen
# -------------------------

def show_login(info=None):

    clear_window()

    root.geometry("900x600")

    container = tk.Frame(root, bg=BG)
    container.place(relx=0.5, rely=0.5, anchor="center")

    tk.Label(
        container,
        text="MESSENGER",
        font=("Segoe UI", 28, "bold"),
        bg=BG,
        fg=TEXT
    ).pack(pady=(0, 5))

    tk.Label(
        container,
        text="Connect with everyone.",
        font=("Segoe UI", 11),
        bg=BG,
        fg=MUTED
    ).pack(pady=(0, 25))

    card = tk.Frame(
        container,
        bg=PANEL,
        padx=35,
        pady=30
    )
    card.pack()

    tk.Label(
        card,
        text="Welcome back",
        font=("Segoe UI", 19, "bold"),
        bg=PANEL,
        fg=TEXT
    ).pack(anchor="w")

    tk.Label(
        card,
        text="Sign in or create an account",
        bg=PANEL,
        fg=MUTED
    ).pack(anchor="w", pady=(5, 20))

    tk.Label(
        card,
        text="Username",
        bg=PANEL,
        fg=TEXT
    ).pack(anchor="w")

    username_entry = tk.Entry(
        card,
        font=FONT,
        bg=INPUT,
        fg=TEXT,
        insertbackground=TEXT,
        relief="flat",
        width=35
    )
    username_entry.pack(pady=(6, 15), ipady=9)

    tk.Label(
        card,
        text="Password",
        bg=PANEL,
        fg=TEXT
    ).pack(anchor="w")

    password_entry = tk.Entry(
        card,
        font=FONT,
        bg=INPUT,
        fg=TEXT,
        insertbackground=TEXT,
        show="*",
        relief="flat",
        width=35
    )
    password_entry.pack(pady=(6, 15), ipady=9)

    info_label = tk.Label(
        card,
        text=info or "",
        bg=PANEL,
        fg=RED,
        wraplength=280
    )
    info_label.pack(pady=5)

    def authenticate(action):

        username = username_entry.get().strip()
        password = password_entry.get()

        if not username or not password:
            messagebox.showwarning(
                "Missing information",
                "Please enter username and password."
            )
            return

        if action == "register":
            confirm = confirm_entry.get()

            if password != confirm:
                messagebox.showerror(
                    "Error",
                    "Passwords do not match."
                )
                return

        try:
            auth_response.clear()

            send_request({
                "action": action,
                "username": username,
                "password": password
            })

            set_status("Authenticating...", ACCENT)

        except OSError as exc:
            messagebox.showerror("Connection Error", str(exc))

    login_btn = tk.Button(
        card,
        text="SIGN IN",
        font=("Segoe UI", 10, "bold"),
        bg=ACCENT,
        fg="white",
        activebackground="#4f46e5",
        activeforeground="white",
        relief="flat",
        cursor="hand2",
        width=35,
        pady=10,
        command=lambda: authenticate("login")
    )
    login_btn.pack(pady=(10, 8))

    confirm_entry = tk.Entry(
        card,
        font=FONT,
        bg=INPUT,
        fg=TEXT,
        insertbackground=TEXT,
        show="*",
        relief="flat",
        width=35
    )

    tk.Label(
        card,
        text="Confirm password (for registration)",
        bg=PANEL,
        fg=MUTED
    ).pack(anchor="w", pady=(10, 0))

    confirm_entry.pack(pady=(6, 10), ipady=9)

    tk.Button(
        card,
        text="CREATE ACCOUNT",
        font=("Segoe UI", 10, "bold"),
        bg="#273449",
        fg=TEXT,
        activebackground="#334155",
        relief="flat",
        cursor="hand2",
        width=35,
        pady=10,
        command=lambda: authenticate("register")
    ).pack()

    username_entry.focus_set()

    set_status(
        "Connected" if connected.is_set() else "Disconnected",
        GREEN if connected.is_set() else RED
    )


# -------------------------
# Chat Screen
# -------------------------

def show_chat():

    global chat_box, status_label

    clear_window()

    root.geometry("1000x650")

    # Sidebar
    sidebar = tk.Frame(
        root,
        bg=PANEL,
        width=230
    )
    sidebar.pack(side="left", fill="y")
    sidebar.pack_propagate(False)

    tk.Label(
        sidebar,
        text="MESSENGER",
        font=("Segoe UI", 18, "bold"),
        bg=PANEL,
        fg=TEXT
    ).pack(pady=(25, 35))

    tk.Label(
        sidebar,
        text="ACCOUNT",
        font=("Segoe UI", 9, "bold"),
        bg=PANEL,
        fg=MUTED
    ).pack(anchor="w", padx=20)

    tk.Label(
        sidebar,
        text=current_username or "",
        font=("Segoe UI", 13, "bold"),
        bg=PANEL,
        fg=TEXT
    ).pack(anchor="w", padx=20, pady=(8, 25))

    tk.Label(
        sidebar,
        text="PUBLIC CHAT",
        bg=PANEL,
        fg=ACCENT,
        font=("Segoe UI", 10, "bold")
    ).pack(anchor="w", padx=20, pady=10)

    tk.Label(
        sidebar,
        text="[messege]",
        bg=PANEL,
        fg=MUTED,
        justify="left"
    ).pack(anchor="w", padx=20)

    tk.Label(
        sidebar,
        text="PRIVATE CHAT",
        bg=PANEL,
        fg=ACCENT,
        font=("Segoe UI", 10, "bold")
    ).pack(anchor="w", padx=20, pady=(25, 10))

    tk.Label(
        sidebar,
        text="PRVC [username] [message]",
        bg=PANEL,
        fg=MUTED,
        justify="left"
    ).pack(anchor="w", padx=20)

    tk.Button(
        sidebar,
        text="LOG OUT",
        bg="#3b2028",
        fg="#fca5a5",
        activebackground="#572b35",
        relief="flat",
        cursor="hand2",
        pady=10,
        command=logout
    ).pack(side="bottom", fill="x", padx=15, pady=20)

    # Main area
    main = tk.Frame(root, bg=BG)
    main.pack(side="right", fill="both", expand=True)

    header = tk.Frame(main, bg=PANEL, height=65)
    header.pack(fill="x")
    header.pack_propagate(False)

    tk.Label(
        header,
        text="Messages",
        font=("Segoe UI", 17, "bold"),
        bg=PANEL,
        fg=TEXT
    ).pack(side="left", padx=25, pady=15)

    status_label = tk.Label(
        header,
        text="● Connected",
        bg=PANEL,
        fg=GREEN,
        font=FONT
    )
    status_label.pack(side="right", padx=20)

    # Messages
    chat_frame = tk.Frame(main, bg=BG)
    chat_frame.pack(fill="both", expand=True, padx=20, pady=20)

    scrollbar = tk.Scrollbar(chat_frame)
    scrollbar.pack(side="right", fill="y")

    chat_box = tk.Text(
        chat_frame,
        bg=BG,
        fg=TEXT,
        font=("Segoe UI", 11),
        relief="flat",
        wrap="word",
        state="disabled",
        yscrollcommand=scrollbar.set,
        padx=12,
        pady=12
    )
    chat_box.pack(fill="both", expand=True)

    scrollbar.config(command=chat_box.yview)

    chat_box.tag_config(
        "me",
        foreground="#818cf8",
        font=("Segoe UI", 11, "bold")
    )

    chat_box.tag_config(
        "other",
        foreground="#38bdf8",
        font=("Segoe UI", 11, "bold")
    )

    chat_box.tag_config(
        "private",
        foreground="#c084fc",
        font=("Segoe UI", 11, "bold")
    )

    chat_box.tag_config(
        "system",
        foreground="#94a3b8",
        font=("Segoe UI", 10, "italic")
    )

    # Message input
    input_frame = tk.Frame(main, bg=PANEL)
    input_frame.pack(fill="x", padx=20, pady=(0, 20))

    message_entry = tk.Entry(
        input_frame,
        font=("Segoe UI", 11),
        bg=INPUT,
        fg=TEXT,
        insertbackground=TEXT,
        relief="flat"
    )
    message_entry.pack(
        side="left",
        fill="x",
        expand=True,
        padx=12,
        pady=12,
        ipady=10
    )


    
    def send_message(event=None):

        message = message_entry.get().strip()

        if not message:
            return

        try:

            if message.lower() == "exit":
                logout()
                return

            parts = message.split(maxsplit=2)

            # Private message
            if parts[0].upper() == "PRVC":

                if len(parts) < 3:
                    messagebox.showinfo(
                        "Private Message",
                        "Usage: PRVC username message"
                    )
                    return

                recipient = parts[1]
                body = parts[2]

                send_request({
                    "action": "chat",
                    "recipient": recipient,
                    "message": body
                })

            # Public message
            else:

                send_request({
                    "action": "chat",
                    "recipient": None,
                    "message": message
                })

            message_entry.delete(0, "end")

        except OSError:
            messagebox.showerror(
                "Connection Error",
                "Could not send message."
            )


    send_btn = tk.Button(
        input_frame,
        text="SEND",
        bg=ACCENT,
        fg="white",
        activebackground="#4f46e5",
        relief="flat",
        cursor="hand2",
        font=("Segoe UI", 10, "bold"),
        padx=22,
        pady=12,
        command=send_message
    )
    send_btn.pack(side="right", padx=10, pady=10)

    message_entry.bind("<Return>", send_message)
    message_entry.focus_set()


# -------------------------
# Logout
# -------------------------

def logout():

    try:
        send_request({"action": "logout"})
    except OSError:
        pass


# -------------------------
# Application
# -------------------------

def on_close():

    stop_reader.set()
    connected.clear()

    try:
        if sock:
            sock.shutdown(socket.SHUT_RDWR)
            sock.close()
    except OSError:
        pass

    root.destroy()


def main():

    show_login()

    try:
        connect()

    except OSError as exc:
        show_login(f"Cannot connect: {exc}")

    saved_username, saved_token = load_session()

    if saved_token and connected.is_set():

        auth_response.clear()

        try:
            send_request({
                "action": "resume",
                "token": saved_token
            })

        except OSError:
            pass

    root.protocol("WM_DELETE_WINDOW", on_close)
    root.mainloop()


if __name__ == "__main__":
    main()

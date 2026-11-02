
<div>
<img src="https://capsule-render.vercel.app/api?type=waving&color=0:06b6d4,100:6366f1&height=100&section=header" width="100%"/>

# Messenger

A simple desktop messaging application built with Python and Tkinter.

Messenger allows users to communicate through public and private messages using a graphical interface. It connects to a remote server using TCP sockets and exchanges messages in JSON format.

## Features

- **Graphical User Interface:** Built with Python Tkinter.
- **User Authentication:** Sign in and create an account.
- **Automatic Login:** Restore your session using a saved authentication token.
- **Public Chat:** Send messages to everyone.
- **Private Chat:** Send messages to a specific user.
- **Real-time Communication:** Receive messages without refreshing.
- **Dark Interface:** A clean, dark-themed desktop design.
- **Cross-platform GUI:** Uses Python's built-in Tkinter library.

## Getting Started

### Download

Download the latest Messenger executable from the [Releases](../../releases) section.

### Run

1. Download the latest release.
2. Extract the downloaded file if necessary.
3. Run `Messenger.exe`.
4. Sign in or create a new account.
5. Start messaging!

No separate Python installation is required when using the packaged executable.

## How to Use

### 1. Create an Account

- Open Messenger.
- Enter your username.
- Enter your password.
- Confirm your password.
- Click **CREATE ACCOUNT**.

### 2. Sign In

Enter your username and password, then click **SIGN IN**.

### 3. Public Messages

Simply type your message in the message box and press Enter or click SEND.

Example:

```text
Hello everyone!
```

Public messages are sent to everyone.

### 4. Private Messages

To send a private message, use the following format:

```text
PRVC username message
```

Example:

```text
PRVC Alex Hello! How are you?
```

Replace `username` with the recipient's username.

### 5. Log Out

Click the **LOG OUT** button in the sidebar to end your session.

## Technology Stack

| Technology  | Purpose                      |
| ----------- | ---------------------------- |
| Python      | Main programming language    |
| Tkinter     | Graphical user interface     |
| Socket      | Network communication        |
| Threading   | Background message receiving |
| JSON        | Data exchange                |
| PyInstaller | Executable packaging         |

## Network Protocol

Messenger communicates with its server using TCP sockets.

Messages are exchanged as JSON objects, with each message terminated by a newline character.

The client supports authentication, session restoration, public messaging, private messaging, and logout operations.

## Development

To run the application from source:

1. Install Python 3.
2. Make sure Tkinter is available.
3. Clone this repository.
4. Run:

```bash
python Messenger.py
```

To build a Windows executable:

```bash
pip install pyinstaller
pyinstaller --onefile --clean --windowed --name Messenger Messenger.py
```

The executable will be generated inside the `dist` directory.

## Notes

- An active server connection is required.
- User accounts and authentication are managed by the remote server.
- The client stores session information locally.
- Message history is not permanently stored by the client.

## License: MIT

<img src="https://capsule-render.vercel.app/api?type=waving&color=0:06b6d4,100:6366f1&height=100&section=footer" width="100%"/>

</div>

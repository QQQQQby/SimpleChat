# SimpleChat

A lightweight chat application consisting of server and client designed using Python3.8. The server utilizes websockets for efficient real-time communication, while the client features a user-friendly interface created with PyQt. SimpleChat offers a seamless chatting experience, with the convenience of cross-platform compatibility and an easy-to-use client-server architecture.

## Features

- Real-time messaging between users
- Easy-to-use graphical interface
- Client-server architecture
- Utilizes websockets for efficient communication
- Built with PyQt for a consistent cross-platform experience

## Requirements

- Python 3.8
- websockets
- PyQt5
- PyInstaller

To install the required libraries, you can run:

```sh
pip install websockets PyQt5 pyinstaller
```

## Getting Started

### Server

To run the server, execute:

```sh
python server.py
```

By default, the server listens on 0.0.0.0:34999. To modify this, adjust the `HOST` and `PORT` values in `server.py`.

Alternatively, you can run the server on Linux using the `nohup` command:

```sh
nohup python server.py &
```

This command runs the server silently in the background, with output redirected to the `nohup.out` file.

For Windows users, you can generate an executable server file using the provided `server2exe.bat` script. This will create an executable file in the `dist` folder. To do this, run:

```sh
server2exe.bat
```

After the script finishes, you will find the generated executable file named `Simple Chat Server.exe` in the `dist` folder.

### Client

To run the command-line client, execute:

```sh
python client.py
```

Alternatively, run the PyQt5 client:

```sh
python client_with_gui.py
```

To modify the server you want to connect, modify the `HOST` and `PORT` values in the `.py` file first. Enter your desired username and start chatting!

To create an executable file, run:

```sh
client2exe.bat
```

You will find the generated executable file named `Simple Chat.exe` in the `dist` folder.
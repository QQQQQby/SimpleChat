pyrcc5 -o images.py images.qrc
pyinstaller -F -w --icon=simple_chat.png client_with_gui.py --name="Simple Chat"
ie4uinit -show
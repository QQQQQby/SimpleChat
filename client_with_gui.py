import asyncio
import json
import sys
import time
import typing

import websockets
from PyQt5.QtCore import QThread, pyqtSignal, Qt
from PyQt5.QtGui import QColor, QFont, QTextBlockFormat, QCloseEvent, QIcon
from PyQt5.QtWidgets import QApplication, QMainWindow, QVBoxLayout, QWidget, QTextEdit, QLineEdit, QPushButton, \
    QDialog, QMessageBox

import images

class SimpleChatClient(QThread):
    show_username_dialog_signal = pyqtSignal()
    confirm_username_signal = pyqtSignal(str)
    display_message_header_signal = pyqtSignal(str, bool)
    display_message_body_signal = pyqtSignal(str)
    display_notification_signal = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.connection = None
        self.username = None
        self.loop = None
        self.username_event = None

    def confirm_username(self, username):
        self.loop.call_soon_threadsafe(asyncio.create_task, self.send_username_handler(username))

    def send_message(self, message):
        self.loop.call_soon_threadsafe(asyncio.create_task, self.send_single_message_handler(message))

    def close_connection(self):
        self.loop.call_soon_threadsafe(asyncio.create_task, self.close_connection_handler())

    async def send(self, message: typing.Union[str, dict]):
        if type(message) is dict:
            message = json.dumps(message)
        await self.connection.send(message)
        await asyncio.sleep(0)

    async def recv(self) -> dict:
        return json.loads(await self.connection.recv())

    async def send_username_handler(self, username):
        assert self.username_event
        self.username = username
        await self.send({
            'type': 'init',
            'username': username
        })
        self.username_event.set()

    async def send_single_message_handler(self, message):
        await self.send({'type': 'chat', 'username': self.username, 'message': message})

    async def receive_handler(self):
        while True:
            data = await self.recv()
            if data['type'] == 'chat':
                self.display_message_header_signal.emit(
                    data['username'] + ' [' +
                    time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(data['timestamp'])) +
                    ']: ', data['username'] == self.username
                )
                self.display_message_body_signal.emit(data['message'])
            elif data['type'] == 'user_online':
                self.display_notification_signal.emit('用户' + data['username'] + '已上线')
            elif data['type'] == 'user_offline':
                self.display_notification_signal.emit('用户' + data['username'] + '已下线')

    async def close_connection_handler(self):
        self.loop.stop()

    async def main_handler(self):
        self.connection = await websockets.connect('ws://101.133.223.4:34999/', ping_interval=None)
        self.show_username_dialog_signal.emit()

        self.loop = asyncio.get_event_loop()
        self.username_event = asyncio.Event()

        await self.username_event.wait()
        assert self.username

        self.confirm_username_signal.emit(self.username)

        data = await self.recv()
        assert data['type'] == 'online_success'
        self.display_notification_signal.emit(
            self.username + '，欢迎！当前在线人数：' + str(data['number_of_online_users'])
        )
        del data

        await self.receive_handler()

    def run(self):
        asyncio.run(self.main_handler())


class CustomTextEdit(QTextEdit):
    def __init__(self, return_key_callback, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.return_key_callback = return_key_callback

    def keyPressEvent(self, event):
        if (event.key() == Qt.Key_Return or event.key() == Qt.Key_Enter) and \
                not event.modifiers() & Qt.ShiftModifier:
            self.return_key_callback()
        else:
            super().keyPressEvent(event)


class UsernameDialog(QDialog):
    def __init__(self, simple_chat_client, main_window):
        super().__init__()

        self.simple_chat_client = simple_chat_client
        self.main_window = main_window

        self.setWindowTitle('Simple Chat')
        self.setFixedWidth(400)
        self.setWindowIcon(QIcon(':/simple_chat.png'))

        layout = QVBoxLayout()

        font = QFont()
        font.setPointSize(12)

        self.line_edit = QLineEdit()
        self.line_edit.setFont(font)
        self.line_edit.setPlaceholderText('输入你的用户名')
        layout.addWidget(self.line_edit)

        self.start_button = QPushButton('开始聊天！')
        self.start_button.setFont(font)
        self.start_button.clicked.connect(self.start)
        layout.addWidget(self.start_button)

        self.setLayout(layout)

        self.simple_chat_client.show_username_dialog_signal.connect(self.show)
        self.simple_chat_client.confirm_username_signal.connect(self.confirm_username)

    def start(self):
        username = self.line_edit.text().strip()

        if username == '':
            QMessageBox.warning(self, '非法用户名', '用户名为空，请重新输入！')
        else:
            self.simple_chat_client.confirm_username(username)

    def confirm_username(self, username):
        QMessageBox.information(self, '成功登录', '欢迎！' + username + '！')
        self.accept()

    def closeEvent(self, a0: QCloseEvent) -> None:
        self.simple_chat_client.close_connection()

    def accept(self) -> None:
        self.main_window.show()
        super().accept()


class MainWindow(QMainWindow):
    def __init__(self, simple_chat_client):
        super().__init__()

        self.simple_chat_client = simple_chat_client

        self.setWindowTitle('Simple Chat')
        self.setGeometry(400, 400, 800, 1000)
        self.setWindowIcon(QIcon(':/simple_chat.png'))

        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        layout = QVBoxLayout()

        self.chat_box = QTextEdit()
        self.chat_box.setReadOnly(True)
        layout.addWidget(self.chat_box)

        font = QFont()
        font.setPointSize(16)
        self.message_input = CustomTextEdit(self.send_message)
        self.message_input.setMaximumHeight(200)
        self.message_input.setPlaceholderText('在此输入你的消息...')
        self.message_input.setFont(font)
        layout.addWidget(self.message_input)

        font = QFont()
        font.setPointSize(12)
        self.send_button = QPushButton('发送')
        self.send_button.setFont(font)
        self.send_button.clicked.connect(self.send_message)
        layout.addWidget(self.send_button)

        central_widget.setLayout(layout)

        self.simple_chat_client.display_message_header_signal.connect(self.display_message_header)
        self.simple_chat_client.display_message_body_signal.connect(self.display_message_body)
        self.simple_chat_client.display_notification_signal.connect(self.display_notification)

    def send_message(self):
        message = self.message_input.toPlainText()
        if not message:
            # QMessageBox.warning(self, '非法输入', '消息不可为空！')
            return
        self.simple_chat_client.send_message(message)
        self.message_input.clear()

    def display_message_header(self, text, is_self):
        self.append_text_to_chat_box(
            text,
            color=(0, 128, 0) if is_self else (0, 0, 255),
            font_size=12,
            font_weight=QFont.Bold
        )

    def display_message_body(self, text):
        self.append_text_to_chat_box(
            text,
            font_size=20,
            paragraph_spacing=20
        )

    def display_notification(self, text):
        self.append_text_to_chat_box(
            text,
            font_size=12,
            color=(128, 128, 128),
            paragraph_spacing=20
        )

    def append_text_to_chat_box(self, text,
                                color=(0, 0, 0), font_family='SimSun', font_size=16, font_weight=QFont.Normal,
                                paragraph_spacing=0):
        self.chat_box.setTextColor(QColor(*color))
        self.chat_box.setFontFamily(font_family)
        self.chat_box.setFontPointSize(font_size)
        self.chat_box.setFontWeight(font_weight)
        self.chat_box.append(text)

        text_block_format = QTextBlockFormat()
        text_block_format.setBottomMargin(paragraph_spacing)
        cursor = self.chat_box.textCursor()
        cursor.setBlockFormat(text_block_format)
        self.chat_box.setTextCursor(cursor)

    def closeEvent(self, a0: QCloseEvent) -> None:
        self.simple_chat_client.close_connection()


if __name__ == '__main__':
    app = QApplication(sys.argv)

    simple_chat_client = SimpleChatClient()
    main_window = MainWindow(simple_chat_client)
    username_dialog = UsernameDialog(simple_chat_client, main_window)

    simple_chat_client.start()

    sys.exit(app.exec_())

import asyncio
import json
import sys
import time
import typing

import websockets
from PyQt5.QtCore import QThread, pyqtSignal, Qt
from PyQt5.QtGui import QTextBlockFormat, QCloseEvent, QIcon, QTextCursor
from PyQt5.QtWidgets import QApplication, QMainWindow, QVBoxLayout, QWidget, QTextEdit, QLineEdit, QPushButton, \
    QDialog, QMessageBox, QHBoxLayout, QSplitter

import images


# TODO: 重连机制；手动选择服务器

class SimpleChatClient(QThread):
    show_username_dialog_signal = pyqtSignal()
    username_dialog_data_ready_signal = pyqtSignal(dict)
    main_window_data_ready_signal = pyqtSignal(dict)

    def __init__(self):
        super().__init__()
        self.connection = None
        self.username = None
        self.loop = None
        self.username_set_event = None

    def set_username(self, username):
        self.loop.call_soon_threadsafe(asyncio.create_task, self.set_username_handler(username))

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

    async def set_username_handler(self, username):
        assert self.username_set_event is not None
        self.username = username
        self.username_set_event.set()

    async def send_single_message_handler(self, message):
        await self.send({'type': 'chat', 'username': self.username, 'message': message})

    async def close_connection_handler(self):
        await self.connection.close()
        self.loop.stop()

    async def main_handler(self):
        self.connection = await websockets.connect('ws://127.0.0.1:34999/', ping_interval=None)

        self.show_username_dialog_signal.emit()

        self.username_set_event = asyncio.Event()
        self.loop = asyncio.get_event_loop()

        await self.username_set_event.wait()

        await self.send({
            'type': 'init',
            'username': self.username
        })
        data = await self.recv()

        while data['type'] != 'online_success':
            self.username_dialog_data_ready_signal.emit(data)

            self.username_set_event.clear()
            await self.username_set_event.wait()

            await self.send({
                'type': 'init',
                'username': self.username
            })
            data = await self.recv()

        assert data['type'] == 'online_success'
        self.username_dialog_data_ready_signal.emit(data)
        self.main_window_data_ready_signal.emit(data)

        while True:
            self.main_window_data_ready_signal.emit(await self.recv())

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
    def __init__(self, simple_chat_client):
        super().__init__()

        self.simple_chat_client = simple_chat_client
        self.simple_chat_client.show_username_dialog_signal.connect(self.show)
        self.simple_chat_client.username_dialog_data_ready_signal.connect(self.on_data_received)

        layout = QHBoxLayout()

        self.username_edit = QLineEdit()
        self.username_edit.setStyleSheet('''
            padding: 6px;
            font-size: 16px;
            border-radius: 8px;
        ''')
        self.username_edit.setPlaceholderText('用户名')
        layout.addWidget(self.username_edit)

        self.start_button = QPushButton('开始')
        self.start_button.setStyleSheet('''
            QPushButton {
                padding: 8px 8px;
                font-size: 14px;
                color: white;
                background-color: #2eab2e;
                border: none;
                border-radius: 8px;
            }
            QPushButton:hover {
                background-color: #2a9c2a;
            }
            QPushButton:pressed {
                background-color: #268c26;
            }
        ''')
        self.start_button.clicked.connect(self.start)
        layout.addWidget(self.start_button)

        self.setLayout(layout)

        self.setWindowTitle('Simple Chat')
        self.setWindowIcon(QIcon(':/simple_chat.png'))
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)

        size = self.sizeHint()
        size.setWidth(int(size.width() * 1.2))
        size.setHeight(int(size.height() * 1.1))
        self.resize(size)
        self.move(QApplication.desktop().screen().rect().center() - self.rect().center())

    def start(self):
        self.username_edit.setEnabled(False)
        self.start_button.setEnabled(False)

        username = self.username_edit.text().strip()
        self.simple_chat_client.set_username(username)

    def on_data_received(self, data: dict):
        self.username_edit.setEnabled(True)
        self.start_button.setEnabled(True)

        if data['type'] == 'online_success':
            QMessageBox.information(self, '成功登录', self.simple_chat_client.username + '，欢迎！')
            self.accept()

        elif data['type'] == 'empty_username':
            QMessageBox.warning(self, '登录失败', '用户名不可为空！')

        elif data['type'] == 'duplicate_username':
            QMessageBox.warning(self, '登录失败', '已存在该用户名！')

        else:
            raise Exception('unexpected data received')

    def closeEvent(self, a0: QCloseEvent) -> None:
        self.simple_chat_client.close_connection()


class MainWindow(QMainWindow):
    def __init__(self, simple_chat_client):
        super().__init__()

        self.number_of_online_users = 0

        self.simple_chat_client = simple_chat_client
        self.simple_chat_client.main_window_data_ready_signal.connect(self.on_data_received)

        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        layout = QVBoxLayout()
        splitter = QSplitter(Qt.Vertical)

        self.chat_box_text_edit = QTextEdit()
        self.chat_box_text_edit.setReadOnly(True)
        self.chat_box_text_edit.setStyleSheet('''
            background: white;
            padding: 0px 3px;
            border: 1px solid #d6d6d6;
            border-radius: 5px;
            font-size: 12px;
        ''')

        self.chat_box_text_edit.verticalScrollBar().setStyleSheet('''
            QScrollBar:vertical {
                width: 11px;
                padding: 3px;
                border: none;
                border-radius: 0px;
                margin: 0px;
            }
            QScrollBar::handle:vertical {
                min-height: 30px;
                background: #dbdbdb;
                border-radius: 2px;
            }
            QScrollBar::handle:vertical:hover {
                background: #a8a8a8;
            }
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
                background: white;
            }
            QScrollBar::add-page:vertical:hover, QScrollBar::sub-page:vertical:hover {
                background: #f1f1f1;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
            }
        ''')
        splitter.addWidget(self.chat_box_text_edit)

        self.message_edit = CustomTextEdit(self.send_message)
        self.message_edit.setStyleSheet(
            self.chat_box_text_edit.styleSheet())
        self.message_edit.verticalScrollBar().setStyleSheet(
            self.chat_box_text_edit.verticalScrollBar().styleSheet())
        splitter.addWidget(self.message_edit)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 1)

        layout.addWidget(splitter)

        self.send_button = QPushButton('发送')
        self.send_button.setStyleSheet('''
            QPushButton {
                padding: 8px 25px;
                font-size: 12px;
                color: white;
                background-color: #2eab2e;
                border: none;
                border-radius: 8px;
            }
            QPushButton:hover {
                background-color: #2a9c2a;
            }
            QPushButton:pressed {
                background-color: #268c26;
            }
        ''')
        self.send_button.clicked.connect(self.send_message)

        send_button_layout = QHBoxLayout()
        send_button_layout.addStretch()
        send_button_layout.addWidget(self.send_button)
        layout.addLayout(send_button_layout)

        central_widget.setLayout(layout)

        self.setWindowTitle('Simple Chat')
        self.setWindowIcon(QIcon(':/simple_chat.png'))

        screen_size = QApplication.primaryScreen().size()
        self.resize(int(screen_size.width() * 0.25), int(screen_size.height() * 0.55))
        self.move(QApplication.desktop().screen().rect().center() - self.rect().center())

        self.message_edit.setFocus()

    def send_message(self):
        message = self.message_edit.toPlainText()
        if not message:
            # QMessageBox.warning(self, '非法输入', '消息不可为空！')
            return
        self.simple_chat_client.send_message(message)
        self.message_edit.clear()

    def on_data_received(self, data):
        if data['type'] == 'chat':

            text = data['username'] + ' [' + \
                   time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(data['timestamp'])) + ']: '
            if data['username'] == self.simple_chat_client.username:
                self.display_self_message_header(text)
            else:
                self.display_message_header(text)
            self.display_message_body(data['message'])

        elif data['type'] == 'user_online':
            self.display_notification('用户' + data['username'] + '已上线')
            self.number_of_online_users += 1
            self.setWindowTitle('Simple Chat - 当前在线人数：' + str(self.number_of_online_users))

        elif data['type'] == 'user_offline':
            self.display_notification('用户' + data['username'] + '已下线')
            self.number_of_online_users -= 1
            self.setWindowTitle('Simple Chat - 当前在线人数：' + str(self.number_of_online_users))

        elif data['type'] == 'online_success':
            # self.display_notification(
            #     self.simple_chat_client.username + '，欢迎！当前在线人数：' + str(data['number_of_online_users'])
            # )
            self.number_of_online_users = data['number_of_online_users']
            self.setWindowTitle('Simple Chat - 当前在线人数：' + str(self.number_of_online_users))

        else:
            raise Exception('unexpected data received')
        self.chat_box_text_edit.moveCursor(QTextCursor.End)

    def display_message_header(self, text):
        style = 'color: #0000a0; font-size: 10px; font-weight: bold;'

        self.chat_box_text_edit.append('<p style=\'' + style + '\'>' + text + '</p>')
        self.set_bottom_margin(0)

    def display_self_message_header(self, text):
        style = 'color: #00a000; font-size: 10px; font-weight: bold'

        self.chat_box_text_edit.append('<p style=\'' + style + '\'>' + text + '</p>')
        self.set_bottom_margin(0)

    def display_message_body(self, text):
        style = 'font-size: 12px;'

        self.chat_box_text_edit.append('<p style=\'' + style + '\'>' + text + '</p>')
        self.set_bottom_margin(15)

    def display_notification(self, text):
        style = 'color: #808080; font-size: 10px;'

        self.chat_box_text_edit.append('<p style=\'' + style + '\'>' + text + '</p>')
        self.set_bottom_margin(15)

    def set_bottom_margin(self, bottom_margin):
        text_block_format = QTextBlockFormat()
        text_block_format.setBottomMargin(bottom_margin)
        self.chat_box_text_edit.textCursor().setBlockFormat(text_block_format)

    def closeEvent(self, a0: QCloseEvent) -> None:
        self.simple_chat_client.close_connection()


if __name__ == '__main__':
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling)
    app = QApplication(sys.argv)

    simple_chat_client = SimpleChatClient()
    username_dialog = UsernameDialog(simple_chat_client)
    main_window = MainWindow(simple_chat_client)

    username_dialog.accepted.connect(main_window.show)

    simple_chat_client.start()

    sys.exit(app.exec_())

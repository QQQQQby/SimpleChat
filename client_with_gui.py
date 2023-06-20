import asyncio
import json
import sys
import time
import typing

import websockets
from PyQt5.QtCore import QThread, pyqtSignal, Qt
from PyQt5.QtGui import QColor, QFont, QTextBlockFormat, QCloseEvent, QIcon, QTextCursor
from PyQt5.QtWidgets import QApplication, QMainWindow, QVBoxLayout, QWidget, QTextEdit, QLineEdit, QPushButton, \
    QDialog, QMessageBox, QDesktopWidget, QHBoxLayout, QSplitter

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
        self.setFixedSize(250, 60)
        self.center()

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

    def center(self):
        geometry = self.frameGeometry()
        geometry.moveCenter(QDesktopWidget().availableGeometry().center())
        self.move(geometry.topLeft())

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
            padding: 6px;
            border: 1px solid #ccc;
            border-radius: 5px;
        ''')
        splitter.addWidget(self.chat_box_text_edit)

        self.message_edit = CustomTextEdit(self.send_message)
        self.message_edit.setStyleSheet('''
            padding: 6px;
            font-size: 20px;
            border: 1px solid #ccc;
            border-radius: 5px;
        ''')
        splitter.addWidget(self.message_edit)

        layout.addWidget(splitter)

        self.send_button = QPushButton('发送')
        self.send_button.setStyleSheet('''
            QPushButton {
                padding: 8px 25px;
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
        self.send_button.clicked.connect(self.send_message)

        send_button_layout = QHBoxLayout()
        send_button_layout.addStretch()
        send_button_layout.addWidget(self.send_button)
        layout.addLayout(send_button_layout)

        central_widget.setLayout(layout)

        self.setWindowTitle('Simple Chat')
        self.setWindowIcon(QIcon(':/simple_chat.png'))
        self.resize(500, 600)
        splitter.setSizes([400, 200])
        self.center()

    def send_message(self):
        message = self.message_edit.toPlainText()
        if not message:
            # QMessageBox.warning(self, '非法输入', '消息不可为空！')
            return
        self.simple_chat_client.send_message(message)
        self.message_edit.clear()

    def on_data_received(self, data):
        if data['type'] == 'chat':
            self.display_message_header(
                data['username'] + ' [' +
                time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(data['timestamp'])) +
                ']: ', data['username'] == self.simple_chat_client.username
            )
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
            font_size=16,
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
        self.chat_box_text_edit.setTextColor(QColor(*color))
        self.chat_box_text_edit.setFontFamily(font_family)
        self.chat_box_text_edit.setFontPointSize(font_size)
        self.chat_box_text_edit.setFontWeight(font_weight)
        self.chat_box_text_edit.append(text)

        text_block_format = QTextBlockFormat()
        text_block_format.setBottomMargin(paragraph_spacing)
        cursor = self.chat_box_text_edit.textCursor()
        cursor.setBlockFormat(text_block_format)
        self.chat_box_text_edit.setTextCursor(cursor)
        self.chat_box_text_edit.moveCursor(QTextCursor.End)

    def center(self):
        self.move(QApplication.desktop().screen().rect().center() - self.rect().center())

    def show(self) -> None:
        self.message_edit.setFocus()
        super().show()

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

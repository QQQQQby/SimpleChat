import asyncio
import time
import typing

import websockets
import json

"""
TODO: 
重连机制
"""


async def send(connection, message: typing.Union[str, dict]):
    if type(message) is dict:
        message = json.dumps(message)
    await connection.send(message)
    await asyncio.sleep(0)


async def recv(connection) -> dict:
    return json.loads(await connection.recv())


async def send_handler(connection, username):
    loop = asyncio.get_event_loop()
    while True:
        await send(connection, {
            'type': 'chat',
            'username': username,
            'message': await loop.run_in_executor(None, input)
        })


async def receive_handler(connection):
    while True:
        data = await recv(connection)
        if data['type'] == 'chat':
            print(data['username'] + ' [' +
                  time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(data['timestamp'])) +
                  ']: ')
            print(data['message'])
        elif data['type'] == 'user_online':
            print('用户' + data['username'] + '已上线')
        elif data['type'] == 'user_offline':
            print('用户' + data['username'] + '已下线')


async def main():
    async with websockets.connect('ws://127.0.0.1:34999/', ping_interval=None) as connection:
        loop = asyncio.get_event_loop()
        username = await loop.run_in_executor(None, input, '输入用户名：')

        await send(connection, {
            'type': 'init',
            'username': username
        })

        data = await recv(connection)
        assert data['type'] == 'online_success'
        print('欢迎！' + username + '。当前在线人数：' + str(data['number_of_online_users']))

        await asyncio.gather(
            send_handler(connection, username),
            receive_handler(connection)
        )


if __name__ == '__main__':
    asyncio.run(main())

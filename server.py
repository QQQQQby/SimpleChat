import asyncio
import json
import time
import typing
from loguru import logger

import websockets
from websockets.exceptions import ConnectionClosed, WebSocketException


# TODO: 禁止用户名重复，若重名或空白则重新输入


# async def heartbeat(websocket, ping_interval):
#     while True:
#         pong_waiter = await websocket.ping()
#         print('ping', end=', ')
#         await pong_waiter
#         print('pong')
#         await asyncio.sleep(ping_interval)
#
#
# def enable_heartbeat(ping_interval=10):
#     def actual_decorator(func):
#         async def wrapper(websocket, *args, **kwargs):
#             heartbeat_task = asyncio.ensure_future(heartbeat(websocket, ping_interval))
#             try:
#                 await func(websocket, *args, **kwargs)
#             finally:
#                 heartbeat_task.cancel()
#
#         return wrapper
#
#     return actual_decorator


def print_execution_time(ending_msg=''):
    def actual_decorator(func):
        async def wrapper(*args, **kwargs):
            t0 = time.time()
            try:
                await func(*args, **kwargs)
            finally:
                print(ending_msg + '(Time duration: ' + str(round(time.time() - t0, 4)) + ' seconds.)')

        return wrapper

    return actual_decorator


connections = dict()
username_to_connection = dict()


async def broadcast_to_all(message: typing.Union[str, dict], excluded_connections=None) -> None:
    if not connections:
        return

    excluded_connections = excluded_connections or set()
    coroutines = [send(conn, message) for conn in connections if conn not in excluded_connections]
    if coroutines:
        await asyncio.wait(coroutines)


async def send(connection, message: typing.Union[str, dict], check_send_event=True) -> None:
    if type(message) is dict:
        message = json.dumps(message)
    if check_send_event:
        await connections[connection][1].wait()
    await connection.send(message)
    await asyncio.sleep(0)


async def client_handler(connection):
    remote_address = connection.remote_address[0] + ':' + str(connection.remote_address[1])
    logger.info('Incoming connection from [' + remote_address + '].')
    try:
        # Read the first message sent by the client and get the username
        data = json.loads(await connection.recv())
        assert data['type'] == 'init'
        username = data['username']
        del data
    except WebSocketException as e:
        logger.warning('The connection with [' + remote_address + '] is closed due to error: ' + str(e))
        return

    # Record information of the user
    username_and_address = '[' + remote_address + '](' + username + ')'
    logger.info(username_and_address + ' connected.')
    send_event = asyncio.Event()
    connections[connection] = (username, send_event)
    username_to_connection[username] = connection
    online_timestamp = int(time.time())

    try:
        # Notify the user of successful login and total number of currently online users
        await send(connection, {
            'type': 'online_success',
            'number_of_online_users': len(connections),
            'timestamp': online_timestamp
        }, False)
        send_event.set()

        # Notify other users that this user is online
        await broadcast_to_all({
            'type': 'user_online',
            'username': username,
            'timestamp': online_timestamp
        }, excluded_connections={connection})
        del online_timestamp

        # Read messages from this user and broadcast them to all the users
        async for message in connection:
            data = json.loads(message)
            assert data['type'] == 'chat'
            data['timestamp'] = int(time.time())
            await broadcast_to_all(data)
            del data

        logger.info(username_and_address + ' disconnected.')

    except ConnectionClosed as e:
        logger.warning(username_and_address + ' disconnected with error: ' + str(e))

    finally:
        # User disconnected
        del connections[connection]
        del username_to_connection[username]

        # Notify other users that this user is offline
        await broadcast_to_all({
            'type': 'user_offline',
            'username': username,
            'timestamp': int(time.time())
        })


@print_execution_time('Server closed.')
async def main(host, port):
    async with websockets.serve(client_handler, host, port) as server:
        logger.info('Server successfully started at [' + host + ':' + str(port) + '].')
        await server.serve_forever()


if __name__ == '__main__':
    asyncio.run(main('0.0.0.0', 34999))

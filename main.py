import json
import sys
import traceback

import uvicorn
from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger
from starlette.websockets import WebSocketDisconnect

from remote_auth import RA

app = FastAPI()

origins = ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.websocket('/ra')
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    logger.remove()
    logger.add(
        sink=sys.stdout,
        level="DEBUG",
        format=f'<cyan>{websocket.client.host:<15}</cyan> | ' + '<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | <level>{level: <8}</level> | <cyan>{name}:{function}</cyan> | <level>{message}</level>',
        colorize=True,
        backtrace=False,
        catch=True,
    )

    ra_instance = RA(callback_on_login=client_login,
                     callback_on_refuse=client_refused_login,
                     callback_on_token=token_received,
                     callback_on_close=connection_closed)
    ra_instance.logger = logger
    ra_instance.client_server_con = websocket
    ra_instance.logger.warning('User connected')

    qr_code = ra_instance.get_qr()
    await websocket.send_text(
        json.dumps({'op': 'qr_code_renew', 'url': qr_code, 'reason': 'first_qr'}))
    ra_instance.logger.debug(f'First QR - {qr_code}')

    while True:
        try:
            await websocket.receive_text()
        except WebSocketDisconnect:
            ra_instance.server_discord_con.close()
            ra_instance.logger.warning('User disconnected from client-server socket')
            break


async def connection_closed(ra_instance):
    await ra_instance.client_server_con.send_text(
        json.dumps({'op': 'changing_qr', 'reason': 'connection_was_closed'}))
    qr_code = ra_instance.get_qr()
    await ra_instance.client_server_con.send_text(
        json.dumps({'op': 'qr_code_renew', 'url': qr_code,
                    'reason': 'previous_webosocket_closed_the_connection'}))

    ra_instance.logger.error(f'Previous connection was closed, new QR - {qr_code}')


async def token_received(ra_instance, token):
    await ra_instance.client_server_con.send_text(json.dumps({'op': 'token_received',
                                                              'token': token}))
    ra_instance.logger.info(f'{token} - Token received')
    await ra_instance.client_server_con.close()


async def client_login(ra_instance, user_id, user_discriminator, user_avatar, user_name):
    await ra_instance.client_server_con.send_text(json.dumps({'op': 'login_attempt',
                                                              'user_id': user_id,
                                                              'user_discriminator': user_discriminator,
                                                              'user_avatar': user_avatar,
                                                              'user_name': user_name}))
    ra_instance.logger.debug(f'{user_name}#{user_discriminator} (user_id) - User logging in')


async def client_refused_login(ra_instance):
    await ra_instance.client_server_con.send_text(
        json.dumps({'op': 'changing_qr', 'reason': 'client_refused_login'}))
    qr_code = ra_instance.get_qr()
    await ra_instance.client_server_con.send_text(
        json.dumps({'op': 'qr_code_renew', 'url': qr_code, 'reason': 'client_refused_login'}))

    ra_instance.logger.debug(f'Client refused login, new QR - {qr_code}')


uvicorn.run(app,
            host='0.0.0.0',
            port=8080,
            # log_level='debug',
            # host='127.0.0.1',
            # port=8080,
            )

import json

import uvicorn
from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware
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
    ra_instance = RA(callback_on_login=client_login,
                     callback_on_refuse=client_refused_login,
                     callback_on_token=token_received,
                     callback_on_close=connection_closed)
    ra_instance.client_server_con = websocket
    await websocket.send_text(
        json.dumps({'op': 'qr_code_renew', 'url': ra_instance.get_qr(), 'reason': 'first_qr'}))

    while True:
        try:
            await websocket.receive_text()
        except WebSocketDisconnect:
            break



async def connection_closed(ra_instance):
    await ra_instance.server_client.send_text(
        json.dumps({'op': 'qr_code_renew', 'url': ra_instance.get_qr(),
                    'reason': 'previous_webosocket_closed_the_connection'}))


async def token_received(ra_instance, token):
    await ra_instance.client_server_con.send_text(json.dumps({'op': 'token_received',
                                                              'token': token}))


async def client_login(ra_instance, user_id, user_discriminator, user_avatar, user_name):
    await ra_instance.client_server_con.send_text(json.dumps({'op': 'login_attempt',
                                                              'user_id': user_id,
                                                              'user_discriminator': user_discriminator,
                                                              'user_avatar': user_avatar,
                                                              'user_name': user_name}))


async def client_refused_login(ra_instance):
    await ra_instance.client_server_con.send_text(
        json.dumps({'op': 'client_refused_login'}))
    await ra_instance.client_server_con.send_text(
        json.dumps({'op': 'qr_code_renew', 'url': ra_instance.get_qr(), 'reason': 'client_refused_login'}))


uvicorn.run(app,
            host='0.0.0.0',
            port=8080,
            log_level='debug'
            )

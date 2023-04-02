import asyncio
import base64
import hashlib
import json
import time
from threading import Thread

import websocket
from cryptography.hazmat.primitives import serialization, hashes
from cryptography.hazmat.primitives.asymmetric import rsa, padding
from loguru import logger

from .config import REMOTE_AUTH_URL, headers

logger.remove()


class RA:
    def __init__(self, callback_on_login, callback_on_refuse, callback_on_token, callback_on_close):
        self._qr_code = None
        self.callback_on_login = callback_on_login
        self.client_refused_login = callback_on_refuse
        self.callback_on_token = callback_on_token
        self.connection_closed = callback_on_close
        server_discord_con = websocket.WebSocketApp(REMOTE_AUTH_URL,
                                                    header=headers,
                                                    on_message=self._on_message,
                                                    on_close=self._on_close)
        server_discord_con.ra_instance = self
        self.server_discord_con = server_discord_con
        Thread(target=server_discord_con.run_forever,
               args=(None, None, 41.250, None, json.dumps({"op": "heartbeat"}))).start()

        # Thread(target=server_discord_con.run_forever).start()

    def get_qr(self):
        while not self._qr_code:
            pass
        return self._qr_code

    @staticmethod
    def _on_close(ws):
        ra_instance = ws.ra_instance
        ra_instance._qr_code = None
        ra_instance.server_discord_con.close()
        server_discord_con = websocket.WebSocketApp(REMOTE_AUTH_URL,
                                                    header=headers,
                                                    on_message=ra_instance._on_message,
                                                    on_close=ra_instance._on_close)
        server_discord_con.ra_instance = ra_instance
        ra_instance.server_discord_con = server_discord_con
        Thread(target=server_discord_con.run_forever,
               args=(None, None, 41.250, None, json.dumps({"op": "heartbeat"}))).start()

        asyncio.run(ra_instance.connection_closed(ra_instance))

    @staticmethod
    def _on_message(ws, message):
        ra_instance = ws.ra_instance
        message = json.loads(message)

        if message['op'] == 'hello':
            rsa_key_pair = rsa.generate_private_key(
                public_exponent=65537,
                key_size=2048
            )

            public_key = rsa_key_pair.public_key().public_bytes(
                serialization.Encoding.DER,
                serialization.PublicFormat.SubjectPublicKeyInfo
            )

            ra_instance._rsa_key_pair = rsa_key_pair
            ra_instance._public_key = public_key

            pk = base64.b64encode(ra_instance._public_key).decode('utf-8')
            ra_instance.server_discord_con.send(json.dumps({
                'op': 'init',
                'encoded_public_key': pk
            }))

        elif message['op'] == 'nonce_proof':
            encrypted_nonce = base64.b64decode(message['encrypted_nonce'])
            decrypted_nonce = ra_instance._rsa_key_pair.decrypt(
                encrypted_nonce,
                padding.OAEP(
                    mgf=padding.MGF1(algorithm=hashes.SHA256()),
                    algorithm=hashes.SHA256(),
                    label=None
                )
            )
            proof = base64.urlsafe_b64encode(hashlib.sha256(decrypted_nonce).digest()).decode('utf-8').replace('=', '')

            ra_instance.server_discord_con.send(json.dumps({
                'op': 'nonce_proof',
                'proof': proof
            }))

        elif message['op'] == 'pending_remote_init':
            fingerprint = message['fingerprint']
            ra_instance._qr_code = 'https://discord.com/ra/' + fingerprint

        elif message['op'] == 'pending_ticket':
            encrypted_user_payload = base64.b64decode(message['encrypted_user_payload'])
            decrypted_user_payload = ra_instance._rsa_key_pair.decrypt(
                encrypted_user_payload,
                padding.OAEP(
                    mgf=padding.MGF1(algorithm=hashes.SHA256()),
                    algorithm=hashes.SHA256(),
                    label=None
                )
            ).decode('utf-8')
            user_id, user_discriminator, user_avatar, user_name = decrypted_user_payload.split(':')
            asyncio.run(
                ra_instance.callback_on_login(ra_instance, user_id, user_discriminator, user_avatar,
                                              user_name))

        elif message['op'] == 'pending_login':
            token = message['ticket']
            asyncio.run(ra_instance.callback_on_token(ra_instance, token))
            ra_instance.server_discord_con.close()

        elif message['op'] == 'cancel':
            ra_instance._qr_code = None
            ra_instance.server_discord_con.close()
            server_discord_con = websocket.WebSocketApp(REMOTE_AUTH_URL,
                                                        header=headers,
                                                        on_message=ra_instance._on_message,
                                                        on_close=ra_instance._on_close)
            server_discord_con.ra_instance = ra_instance
            ra_instance.server_discord_con = server_discord_con
            Thread(target=server_discord_con.run_forever,
                   args=(None, None, 41.250, None, json.dumps({"op": "heartbeat"}))).start()

            asyncio.run(ra_instance.client_refused_login(ra_instance))

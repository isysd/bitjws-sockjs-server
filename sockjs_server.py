import os
import sys
import json
import hmac
import time
import base64
import logging
import hashlib
from binascii import hexlify
from functools import partial
from util import setupLogHandlers

import ecdsa
import onetimepass
from tornado import web, ioloop
from sockjs.tornado import SockJSRouter, SockJSConnection
from sockjs_pika_consumer import AsyncConsumer

import pikaconfig


# Messages clients listen for after connecting.
DEFAULT_MESSAGES = ['sockjsmq']

ERR_UNKNOWN_MSG = json.dumps({'type': 'error', 'reason': 'unknown message'})
ERR_INVALID_DATA = json.dumps({'type': 'error', 'reason': 'invalid data'})
ERR_AUTH_FAILED = json.dumps({'type': 'auth', 'reason': 'bad credentials',
                              'success': False})

TOTP_NDIGITS = 6
TOTP_TIMEOUT = 60 * 10  # 10 minutes


class Connection(SockJSConnection):

    def on_message(self, msg):
        if len(str(msg)) > 1024:
            self.logger.info('rejected message from %s (%s): too large' % (
                self.ip, self))
            self.send(ERR_INVALID_DATA)
            return

        received_at = '%.6f' % time.time()

        self.logger.info('%s @ %s' % (str(msg), received_at))
        # Check if the message received has at least the required fields.
        try:
            data = json.loads(msg)
            if 'type' not in data or 'token' not in data:
                raise Exception("Invalid format, 'type' and/or 'token' missing")
            data['type'] = str(data['type'])
            if data['token'] != self.token:
                if len(data['token']) > 200:
                    data['token'] = data['token'][:200] + '...'
                raise Exception("Invalid token, %s != %s" % (data['token'], self.token))
        except Exception, e:
            self.logger.exception(e)
            self.send(ERR_INVALID_DATA)
            return

        # Handle the incoming message based on the type specified.
        dtype = data['type']
        if dtype == 'auth':
            if not self.consumer.listener_allowed(self, 'transaction'):
                self._handle_auth(data, received_at)
        elif dtype == 'listen':
            self._handle_singlelisten(data, received_at)
        elif dtype == 'ping':
            self._handle_ping(data, received_at)
        else:
            self.logger.info('unknown message: "%s" @ %s' % (
                data['type'], received_at))
            self.send(ERR_UNKNOWN_MSG)

    def on_open(self, info):
        # Take care to use a proxy that ends up passing the right
        # IP here. In general this means watching out for proxies
        # and headers like X-Fowarded-For.
        self.ip = info.ip
        self.token = hexlify(os.urandom(8))
        self.user_id = None
        self.logger.info("%s (%s, %s)" % (self, self.ip, self.token))

        self.auth_token = base64.b32encode(os.urandom(10))

        self.consumer.listener_add(self, DEFAULT_MESSAGES)

        self.send(json.dumps({
            'type': 'open',
            'token': self.token,
            'auth_token': self.auth_token,
            'now': int(time.time())
        }))
        
        # TODO re-implement digest signing for auth

    def on_close(self):
        self.logger.info("close %s" % self)
        self.consumer.listener_delete(self) 


    def _handle_singlelisten(self, data, received_at):
        """Process a "listen" message.

        This allows anyone to listen for any sockjsmq message.
        """
        # Drop access to any other channel.
        self.consumer.listener_set(self, 'sockjsmq')


    def _handle_ping(self, data, received_at):
        """Process a "ping" message.

        A pong is sent back to the user. If there is more than one
        connection open for the same user, all they will receive
        a pong.
        """
        if not self.user_id:
            # User is not logged in, pong only to this connection.
            self.send(json.dumps({'type': 'pong'}))
            return

        msg = json.dumps({'front_type': 'pong', 'type': self.user_id})
        self.consumer.on_message(None, None, None, msg)


    def _handle_auth(self, data, received_at):
        """Process an "auth" message."""

        if 'digest' not in data or 'key' not in data:
            # Invalid message.
            self.logger.info('invalid "auth" message received @ %s' % received_at)
            self.send(ERR_INVALID_DATA)
            return

        key = str(data['key'])
        digest = str(data['digest'])

        # TODO re-implement signature checks

        hotp_interval_no = int(time.time()) / TOTP_TIMEOUT
        # Get 3 expected tokens so it works if our/client's clock is
        # behind or ahead in relation to the actual time.
        for i in (0, -1, 1):
            expected_token = str(onetimepass.get_hotp(self.auth_token, hotp_interval_no + i)).zfill(TOTP_NDIGITS)
            if verify_func(expected_token):
                # Cool, all good.
                self.logger.info('client accepted @ %s' % received_at)
                self.consumer.listener_add(self, ['sockjsmq'])
                self.send(json.dumps({'type': 'auth', 'success': True}))
                break
        else:
            self.logger.info('digest does not match @ %s' % received_at)
            self.send(ERR_AUTH_FAILED)


class SockJSPikaRouter(SockJSRouter):
    def __init__(self, *args, **kwargs):
        super(SockJSPikaRouter, self).__init__(*args, **kwargs)

        logger = logging.getLogger(name='api-stream')
        for h in setupLogHandlers(fname='API-stream.log'):
            logger.addHandler(h)
        logger.setLevel(logging.DEBUG)
        logger.info("Router created")
        self._connection.logger = logger

        consumer = AsyncConsumer(pikaconfig.BROKER_URL, self.io_loop)
        consumer.setup()
        self._connection.consumer = consumer


Router = SockJSPikaRouter(Connection, '')
app = web.Application(Router.urls)

if __name__ == "__main__":
    app.listen(8123)
    ioloop.IOLoop.instance().start()

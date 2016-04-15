import json
import time
import logging
from util import setupLogHandlers


import bitjws
from tornado import web, ioloop
from sockjs.tornado import SockJSRouter, SockJSConnection
from sockjs_pika_consumer import AsyncConsumer

import pikaconfig


ERR_UNKNOWN_MSG = json.dumps({'method': 'error', 'reason': 'unknown message'})
ERR_INVALID_DATA = json.dumps({'method': 'error', 'reason': 'invalid data'})
ERR_AUTH_FAILED = json.dumps({'method': 'error', 'reason': 'bad credentials'})

TOTP_NDIGITS = 6
TOTP_TIMEOUT = 60 * 10  # 10 minutes


class Connection(SockJSConnection):
    schemas = pikaconfig.SCHEMAS

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
            payload_data = bitjws.validate_deserialize(msg)[1]['data']
            if 'method' not in payload_data:
                self.logger.info("method not in payload data")
                self.send(ERR_UNKNOWN_MSG)  # method is required
                return
        except Exception, e:
            self.logger.exception(e)
            self.send(ERR_INVALID_DATA)
            return
        self.logger.info(payload_data)
        # Handle the incoming message based on the method specified.
        if payload_data['method'] == 'GET':
            if 'model' not in payload_data:
                self.logger.info("model not in payload data")
                self.send(ERR_UNKNOWN_MSG)  # model is required
                return
            allowed = self.consumer.listener_allowed(self, msg)
            self.logger.info(allowed)
            if not allowed:
                self.logger.info("authentication failed")
                self.send(ERR_AUTH_FAILED)
                return
            if 'id' in payload_data:
                lname = "%s_id_%s" % (payload_data['model'], payload_data['id'])
            else:
                lname = payload_data['model']
            self.logger.info('adding listener to %s' % lname)
            self.consumer.listener_add(self, [lname])
        elif payload_data['method'] == 'ping':
            self._handle_ping(payload_data, received_at)
        else:
            self.logger.info('unknown message: "%s" @ %s' % (
                payload_data['method'], received_at))
            self.send(ERR_UNKNOWN_MSG)

    def on_open(self, info):
        # Take care to use a proxy that ends up passing the right
        # IP here. In general this means watching out for proxies
        # and headers like X-Fowarded-For.
        self.ip = info.ip
        self.user_id = None
        self.logger.info("%s (%s)" % (self, self.ip))

        self.send(json.dumps({
            'method': 'open',
            'now': int(time.time()),
            'schemas': self.schemas
        }))

    def on_close(self):
        self.logger.info("close %s" % self)
        self.consumer.listener_delete(self)

    def _handle_ping(self, data, received_at):
        """Process a "ping" message.

        A pong is sent back to the user. If there is more than one
        connection open for the same user, all they will receive
        a pong.
        """
        if not self.user_id:
            # User is not logged in, pong only to this connection.
            self.send(json.dumps({'method': 'pong'}))
            return

        msg = json.dumps({'method': 'pong', 'for': self.user_id})
        self.consumer.on_message(None, None, None, msg)


class SockJSPikaRouter(SockJSRouter):
    def __init__(self, connection, *args, **kwargs):
        super(SockJSPikaRouter, self).__init__(connection, *args, **kwargs)

        logger = logging.getLogger(name='api-stream')
        for h in setupLogHandlers(fname='API-stream.log'):
            logger.addHandler(h)
        logger.setLevel(logging.DEBUG)
        logger.info("Router created")
        self._connection.logger = logger

        consumer = AsyncConsumer(pikaconfig, self.io_loop)
        consumer.setup()
        self._connection.consumer = consumer


Router = SockJSPikaRouter(Connection, '')
app = web.Application(Router.urls)

if __name__ == "__main__":
    app.listen(8123)
    ioloop.IOLoop.instance().start()

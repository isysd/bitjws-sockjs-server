import os
import sys
import json
import time
import hmac
import socket
import hashlib
import unittest
import websocket
from bitcoin.wallet import CKey, P2PKHBitcoinAddress
from mrest_client.client import MRESTClient
from mrest_auth.auth import prepare_mrest_message, pack_message

# Prepend the directory with API clients to the sys path.
CLIENT_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    'client')
if CLIENT_DIR not in sys.path:
    sys.path.insert(0, CLIENT_DIR)

TEST_URL = os.environ.get('WSOCK_URL', 'ws://localhost:8123/websocket')
newcoin = {'metal': 'UB', 'mint': 'Mars global'}

privkey = CKey(os.urandom(64))
pubhash = str(P2PKHBitcoinAddress.from_pubkey(privkey.pub))
keyring = [pubhash]

mrestClient = MRESTClient({'url': 'http://0.0.0.0:8002',
                           'privkey': privkey, 'keyring': keyring})
mrestClient.update_server_info(accept_keys=True)
mrestClient.post("user", {'pubhash': pubhash, 'username': pubhash[0:8]})


def client_wait_for(client, method, model=None, n=20):
    # Assume one of the next n messages will be the
    # one with the desired type on it.
    print method
    print model
    while n:
        n -= 1
        msg = client.recv()
        print msg
        data = json.loads(msg)
        if 'method' in data and data['method'] == method:
            if model is None:
                return data
            elif 'model' in data and data['model'] == model:
                return data


class CommonTestMixin(object):

    def setup(self):
        self.client = websocket.create_connection(TEST_URL)

    def wait_for(self, mtype, n=20):
        return client_wait_for(self.client, mtype, n)


class GoodClient(unittest.TestCase, CommonTestMixin):

    def setUp(self):
        super(GoodClient, self).setup()

    def test_open(self):
        # Test that the first message upon connection is an 'open' message.
        msg = self.client.recv()
        try:
            data = json.loads(msg)
        except Exception, e:
            self.fail("Unexpected error: %s" % e)
        self.assertIn('schemas', data)
        self.assertIn('now', data)

    def test_ping(self):
        self.client.send(json.dumps({'method': 'ping'}))
        try:
            data = client_wait_for(self.client, 'pong')
        except Exception, e:
            self.fail("Unexpected error: %s" % e)
        self.assertIn('method', data)
        self.assertEqual(data['method'], 'pong')

    def test_auth(self):
        headers, data = prepare_mrest_message('GET', data="", pubhash=pubhash, privkey=privkey, headers=None, permissions=['authenticate'])
        packedmess = pack_message('GET', data, headers)
        packedmess['model'] = 'coin'
        self.client.send(json.dumps(packedmess))
        try:
            data = client_wait_for(self.client, 'RESPONSE', 'coin')
        except Exception, e:
            print e
            self.fail("Unexpected error: %s" % e)

        self.assertEqual(data['method'], 'RESPONSE')


class BadClient(unittest.TestCase, CommonTestMixin):

    def setUp(self):
        super(BadClient, self).setup()

    def test_missing_basic(self):
        open_data = json.loads(self.client.recv())

        self.client.send(json.dumps({'type': 'auth'}))
        data = self.wait_for('error')
        if data is None:
            self.fail('no error message received')
        self.assertIn('reason', data)

        self.client.send(json.dumps({'token': open_data['token']}))

    def test_invalid_token(self):
        open_data = json.loads(self.client.recv())
        token = open_data['token']

        for t in (token + 'x', token[:-1] + 'x', '', '0.123', 'x' * 200000):
            self.client.send(json.dumps({'type': 'auth', 'token': t}))
            data = self.wait_for('error')
            if data is None:
                self.fail('no error message received')
            self.assertIn('reason', data)

    def test_unknown_mtype(self):
        open_data = json.loads(self.client.recv())
        token = open_data['token']

        # None of the following types are recognized by the current server.
        for mtype in ('open', 'close', 'error', 'debug', 'info', 'admin', '', 'auth' * 100):
            self.client.send(json.dumps({'type': mtype, 'token': token}))
            data = self.wait_for('error')
            if data is None:
                self.fail('no error message received')
            self.assertIn('reason', data)

    def test_otp_wronginterval(self):
        open_data = json.loads(self.client.recv())
        token = open_data['token']

        # Invalid interval for the protocol used.
        for i in (60, 30, 1, 200, 2 ** 64 - 1):  # n >= 0 for '>Q' packing
            digest = self.sign_token(open_data['auth_token'], interval=int(time.time()) / i)

            data = {'type': 'auth', 'token': token, 'key': self.key, 'digest': digest}
            self.client.send(json.dumps(data))

            result = self.wait_for('auth')
            if result is None:
                self.fail('no auth message received for interval "%s"' % i)
            self.assertIn('success', result)
            self.assertEqual(result['success'], False)
            self.assertIn('reason', result)
            self.assertIsInstance(result['reason'], unicode)

    def test_otp_outofsync(self):
        open_data = json.loads(self.client.recv())
        token = open_data['token']

        # Assumption: this code is running in the same place where the
        # websocket server, therefore the clock here is the same as the
        # the clock in the websocket server.

        # The following digests would be valid, but since we fake
        # out of sync clocks they must fail. Note that the server
        # accepts that tokens that are behind 1 interval, as well
        # those that are 1 interval ahead.

        for i in (-2, 2, 3, -3, 100, 500, -100, -500):
            interval = int(time.time()) / (60 * 10)
            digest = self.sign_token(open_data['auth_token'], interval=interval + i)

            data = {'type': 'auth', 'token': token, 'key': self.key, 'digest': digest}
            self.client.send(json.dumps(data))

            result = self.wait_for('auth')
            if result is None:
                self.fail('no auth message received for interval "%s"' % interval)
            self.assertIn('success', result)
            self.assertEqual(result['success'], False)
            self.assertIn('reason', result)
            self.assertIsInstance(result['reason'], unicode)

    def test_hijack_token(self):
        # In this case, client A opens a connection and receives some token A.
        # This token must be present in every message sent to the server.
        tokenA = json.loads(self.client.recv())['token']

        # Then a client B comes..
        clientB = websocket.create_connection(TEST_URL)
        #keysB = common.createCoinapultAccount(testnet=COINAPULT_TESTNET)[0]
        open_data = json.loads(clientB.recv())
        tokenB = open_data['token']
        self.assertNotEqual(tokenA, tokenB)
        # grabs token A
        tokenB = tokenA
        # and tries to make requests using that.
        data = {'type': 'auth', 'key': keysB['key'],
                'digest': sign_token_hmac(keysB['secret'], open_data['auth_token']),
                'token': tokenB}
        clientB.send(json.dumps(data))

        # In this case, client B should never receive an auth message as
        # the reply. It must fail before the server even decides to route
        # the message.
        result = client_wait_for(clientB, 'error')
        if result is None:
            self.fail('no error message received')
        self.assertIn('reason', result)
        self.assertIsInstance(result['reason'], unicode)

    def test_hijack_authtoken(self):
        # This situation is similar to the previous one, but now
        # client B realized he can't use tokens from other connections.
        # Now the focus is on trying to use auth_token.
        authA = json.loads(self.client.recv())['auth_token']

        clientB = websocket.create_connection(TEST_URL)
        #keysB = common.createCoinapultAccount(testnet=COINAPULT_TESTNET)[0]
        open_data = json.loads(clientB.recv())
        authB = open_data['auth_token']
        self.assertNotEqual(authA, authB)

        # Client B grabs auth_token from client A
        authB = authA
        # and tries to auth using that.
        data = {'type': 'auth', 'key': keysB['key'],
                'digest': sign_token_hmac(keysB['secret'], authB),
                'token': open_data['token']}
        clientB.send(json.dumps(data))

        # In this case everything is correct, but the authentication
        # must not succeed as the auth token used was not given to
        # this client.
        result = client_wait_for(clientB, 'auth')
        if result is None:
            self.fail('no auth message received')
        self.assertIn('reason', result)
        self.assertEqual(result['success'], False)


class MessageLeak(unittest.TestCase, CommonTestMixin):
    """
    This test checks whether unknown messages are leaked to the user.
    In effect this checks how the consumer handles this situation.
    """

    def setUp(self):
        super(MessageLeak, self).setup()

    def test_noleak_unauth(self):
        data = json.loads(self.client.recv())

        # 'ticker2' is unknown, therefore should never get to the user.
        publisherDummy.publish('ticker2', {'index': 600})

        self.client.settimeout(0.5)
        try:
            data = self.wait_for('ticker2')
        except socket.timeout:
            # Good
            pass
        else:
            if data is not None:
                self.fail('ticker2 message received')

    def test_noleak_auth(self):
        data = json.loads(self.client.recv())
        self.auth(data['token'], data['auth_token'])

        # 'transaction' messages should be discarded by the consumer.
        # It is expected to describe them by user id.
        publisherDummy.publish('transaction', {'blurb': 1})
        self.client.settimeout(0.5)
        try:
            data = self.wait_for('transaction')
        except socket.timeout:
            # Good
            pass
        else:
            if data is not None:
                self.fail('transaction message received')


if __name__ == '__main__':
    broken = False

    if len(sys.argv) > 1:
        TEST_REAL_TICKER = True

    test_suite = []
    #for cls in (GoodClient, BadClient, MessageLeak):
    #    test_suite.append(unittest.TestLoader().loadTestsFromTestCase(cls))
    test_suite.append(unittest.TestLoader().loadTestsFromTestCase(GoodClient))

    for i in range(1, 2):
        if broken:
            break
        print 'running test #' + str(i)

        for suite in test_suite:
            time.sleep(0.1)
            result = unittest.TextTestRunner(verbosity=2).run(suite)
            if len(result.errors) > 0 or len(result.failures) > 0:
                broken = True

    if broken:
        raise SystemExit(1)

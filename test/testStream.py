import os
import sys
import json
import time
import unittest

import websocket
import bitjws
from bravado_bitjws.client import BitJWSSwaggerClient
import pika

# Prepend the parent directory to the sys path.
CLIENT_DIR = ".."
if CLIENT_DIR not in sys.path:
    sys.path.insert(0, CLIENT_DIR)

import pikaconfig

TEST_URL = os.environ.get('WSOCK_URL', 'ws://localhost:8123/websocket')

privkey = bitjws.PrivateKey()
pubhash = bitjws.pubkey_to_addr(privkey.pubkey.serialize())

url = 'http://0.0.0.0:8002/'
specurl = '%sstatic/swagger.json' % url

# Tries eo set up bitjws client
try:
    bitjws_client = BitJWSSwaggerClient.from_url(specurl,
                                                 privkey=privkey,
                                                 aud='/response')
    username = str(pubhash)[0:8]
    luser = bitjws_client.get_model('User')(username=username)
    user = bitjws_client.user.addUser(user=luser).result()
except:
    bitjws_client = None
    print "Could not connet to BitJWS server... Continuing without it."
    pass

# Sets up pika for rabbitmq interaction
pika_url_parameters = pika.URLParameters(pikaconfig.BROKER_URL)
pika_client = pika.BlockingConnection(pika_url_parameters)
pika_channel = pika_client.channel()
pika_channel.exchange_declare(**pikaconfig.EXCHANGE)


def client_wait_for(client, method, model=None, n=20):
    """
    Waits for `n` messages expecting one with method `method` and
    returns its payload if found.
    """
    while n:
        n -= 1
        msg = client.recv()
        try:
            payload = bitjws.validate_deserialize(msg)[1]
            data = payload['data']
        except Exception:
            try:
                data = json.loads(msg)
            except Exception:
                return
        if 'method' in data and data['method'] == method:
            if model is None:
                return data
            elif 'model' in data and data['model'] == model:
                return payload


class CommonTestMixin(object):

    def setup(self):
        self.client = websocket.create_connection(TEST_URL)

    def wait_for(self, mtype, n=20):
        return client_wait_for(self.client, mtype, n)

    def tearDown(self):
        self.client.close()


class GoodClient(unittest.TestCase, CommonTestMixin):
    """
    This test case tests how this server handles expected messages from
    a good client.
    """

    def setUp(self):
        super(GoodClient, self).setup()

    def test_open(self):
        # Test that the first message upon connection is an 'open' message.
        msg = self.client.recv()
        try:
            data = json.loads(msg)
        except Exception, e:
            self.fail("Unexpected error: %s" % e)
        # self.assertIn('schemas', data)
        self.assertIn('now', data)

    def test_ping(self):
        msg_data = {'method': 'ping'}
        bitjws_msg = bitjws.sign_serialize(privkey,
                                           data=msg_data,
                                           iat=time.time())
        self.client.send(bitjws_msg)
        try:
            response_msg = client_wait_for(self.client, 'pong')
        except Exception, e:
            self.fail("Unexpected error: %s" % e)
        self.assertIn('method', response_msg)
        self.assertEqual(response_msg['method'], 'pong')

    def test_get_coins(self):
        msg_data = {'method': 'GET',
                    'pubhash': pubhash,
                    'permissions': ['authenticate'],
                    'headers': None,
                    'model': 'coin'}

        bitjws_msg = bitjws.sign_serialize(privkey,
                                           data=msg_data,
                                           iat=time.time())

        self.client.send(bitjws_msg)

        mdata = {'metal': 'testinium', 'mint': 'testStream.py'}
        msg_data = {'method': 'RESPONSE',
                    'metal': mdata['metal'],
                    'mint': mdata['mint'],
                    'pubhash': pubhash,
                    'headers': {},
                    'permissions': ['authenticate'],
                    'model': 'coin'}

        bitjws_msg = bitjws.sign_serialize(privkey,
                                           data=msg_data,
                                           iat=time.time())

        pika_channel.basic_publish(body=bitjws_msg,
                                   exchange=pikaconfig.EXCHANGE['exchange'],
                                   routing_key='')

        try:
            msg_response = client_wait_for(self.client, 'RESPONSE', 'coin')
        except Exception, e:
            self.fail("Unexpected error: %s" % e)

        self.assertIn('data', msg_response)

        data = msg_response['data']
        self.assertEqual(data['metal'], mdata['metal'])
        self.assertEqual(data['mint'], mdata['mint'])

    def test_get_coin_id(self):
        msg_data = {'method': 'GET',
                    'data': '',
                    'pubhash': pubhash,
                    'permissions': ['authenticate'],
                    'headers': None,
                    'model': 'coin',
                    'id': 1337}

        bitjws_msg = bitjws.sign_serialize(privkey,
                                           data=msg_data,
                                           iat=time.time())

        self.client.send(bitjws_msg)

        mdata = {'metal': 'testinium', 'mint': 'testStream.py'}
        msg_data = {'method': 'RESPONSE',
                    'metal': mdata['metal'],
                    'mint': mdata['mint'],
                    'pubhash': pubhash,
                    'headers': {},
                    'permissions': ['authenticate'],
                    'model': 'coin',
                    'id': 1337}

        bitjws_msg = bitjws.sign_serialize(privkey,
                                           data=msg_data,
                                           iat=time.time())

        pika_channel.basic_publish(body=bitjws_msg,
                                   exchange=pikaconfig.EXCHANGE['exchange'],
                                   routing_key='')
        try:
            msg_response = client_wait_for(self.client, 'RESPONSE', 'coin')
        except Exception, e:
            self.fail("Unexpected error: %s" % e)

        self.assertIn('data', msg_response)

        data = msg_response['data']
        self.assertEqual(data['id'], 1337)
        self.assertEqual(data['metal'], mdata['metal'])
        self.assertEqual(data['mint'], mdata['mint'])


class BadClient(unittest.TestCase, CommonTestMixin):
    """
    This test case tests how this server handles unexpected messages from
    a bad client.
    """

    def setUp(self):
        super(BadClient, self).setup()

    def test_get_bad_format(self):
        msg_data = {'data': '',  # no method
                    'pubhash': pubhash,
                    'headers': None,
                    'permissions': ['authenticate'],
                    'model': 'coin'}

        bitjws_msg = bitjws.sign_serialize(privkey,
                                           data=msg_data,
                                           iat=time.time())

        self.client.send(bitjws_msg)

        try:
            msg_response = client_wait_for(self.client, 'error')
        except Exception, e:
            self.fail("Unexpected error: %s" % e)

        self.assertEqual(msg_response['reason'], 'unknown message')

        msg_data = {'data': '',
                    'method': 'GET',
                    'pubhash': pubhash,
                    'headers': None,
                    'permissions': ['authenticate']}  # no model

        bitjws_msg = bitjws.sign_serialize(privkey,
                                           data=msg_data,
                                           iat=time.time())

        self.client.send(bitjws_msg)

        try:
            msg_response = client_wait_for(self.client, 'error')
        except Exception, e:
            self.fail("Unexpected error: %s" % e)

        self.assertEqual(msg_response['reason'], 'unknown message')

    def test_get_coins_bad_sign(self):
        privkey2 = bitjws.PrivateKey()

        msg_data = {'method': 'GET',
                    'data': '',
                    'pubhash': pubhash,
                    'headers': None,
                    'permissions': ['authenticate'],
                    'model': 'coin'}

        # same data but different `privkey`s
        bitjws_msg = bitjws.sign_serialize(privkey, data=msg_data)
        bitjws_msg2 = bitjws.sign_serialize(privkey2, data=msg_data)

        # shifts signatures
        signature2 = bitjws_msg2.split('.')[2]
        bad_signed_msg = '.'.join(bitjws_msg.split('.')[0:2]) + '.' + signature2

        self.client.send(bad_signed_msg)

        try:
            msg_response = client_wait_for(self.client, 'error')
        except Exception, e:
            self.fail("Unexpected error: %s" % e)

        # returning 'invalid data' for now on bad signature; maybe returning
        # 'bad credentials' again in the future.
        self.assertEqual(msg_response['reason'], 'invalid data')

    # def test_subscribe_bad_id(self):
    #     if bitjws_client is None:
    #         print "BitJWS Client not running. "\
    #             + "Ignoring 'test_subscribe_bad_id'..."
    #         return
    #
    #     # create a new user to create his own coin
    #     privkey2 = bitjws.PrivateKey()
    #     pubhash2 = bitjws.pubkey_to_addr(privkey2.pubkey.serialize())
    #     bitjws_client2 = BitJWSSwaggerClient.from_url(specurl)
    #     username2 = str(pubhash2)[0:8]
    #     luser2 = bitjws_client2.get_model('User')(username=username2)
    #     bitjws_client2.user.addUser(user=luser2).result()
    #
    #     # create a coin owned by the new user
    #     lcoin = bitjws_client2.get_model('Coin')(metal='testinium',
    #                                              mint='testStream.py')
    #     coin = bitjws_client2.coin.addCoin(coin=lcoin).result()
    #
    #     # subscribe to the id with the original keys
    #     msg_data = {'method': 'GET',
    #                 'data': '',
    #                 'pubhash': pubhash,
    #                 'headers': None,
    #                 'permissions': ['authenticate'],
    #                 'model': 'coin',
    #                 'id': coin.id}
    #
    #     bitjws_msg = bitjws.sign_serialize(privkey, data=msg_data)
    #
    #     self.client.send(bitjws_msg)
    #
    #     msg_data = {'method': 'RESPONSE',
    #                 'pubhash': pubhash,
    #                 'headers': {},
    #                 'metal': 'testinium',
    #                 'mint': 'testStream.py',
    #                 'permissions': ['authenticate'],
    #                 'model': 'coin',
    #                 'id': coin.id}
    #
    #     bitjws_msg = bitjws.sign_serialize(privkey, data=msg_data,)
    #
    #     pika_channel.basic_publish(body=bitjws_msg,
    #                                exchange=pikaconfig.EXCHANGE['exchange'],
    #                                routing_key='')
    #
    #     for i in range(5):
    #         ping_msg = bitjws.sign_serialize(privkey, method='ping')
    #         self.client.send(ping_msg)
    #
    #     try:
    #         msg_response = client_wait_for(self.client, 'RESPONSE', 'coin')
    #     except Exception, e:
    #         self.fail("Unexpected error: %s" % e)
    #
    #     self.assertIn('data', msg_response)
    #
    #     data = msg_response['data']
    #     self.assertEqual(data['id'], coin.id)
    #     self.assertEqual(data['metal'], 'testinium')
    #     self.assertEqual(data['mint'], 'testStream.py')


class MessageLeak(unittest.TestCase):
    """
    This test case checks whether unknown messages are leaked to the user.
    In effect it checks how the consumer handles this situation.
    """

    def test_connect_publish_coin(self):
        ctm = CommonTestMixin()
        ctm.setup()
        client = ctm.client

        # publish coin message which should not be received by client
        mdata = {'metal': 'testinium', 'mint': 'testStream.py'}
        msg_data = {'method': 'RESPONSE',
                    'metal': mdata['metal'],
                    'mint': mdata['mint'],
                    'pubhash': pubhash,
                    'headers': {},
                    'model': 'coin',
                    'permissions': ['authenticate']}

        bitjws_msg = bitjws.sign_serialize(privkey, data=msg_data)

        pika_channel.basic_publish(body=bitjws_msg,
                                   exchange=pikaconfig.EXCHANGE['exchange'],
                                   routing_key='')

        # publish pings to fill queue
        ping_msg_data = {'method': 'ping'}
        bitjws_ping_msg = bitjws.sign_serialize(privkey, data=ping_msg_data)
        for i in range(5):
            client.send(bitjws_ping_msg)

        try:
            data = client_wait_for(client, 'RESPONSE', 'coin', 5)
        except Exception, e:
            self.fail("Unexpected error: %s" % e)
        self.assertIsNone(data)
        client.close()

    def test_connect_publish_coin_id(self):
        ctm = CommonTestMixin()
        ctm.setup()
        client = ctm.client

        # subscribe to a specific coin id
        msg_data = {'method': 'GET',
                    'data': '',
                    'pubhash': pubhash,
                    'headers': None,
                    'model': 'coin',
                    'permissions': ['authenticate'],
                    'id': 1337}

        bitjws_msg = bitjws.sign_serialize(privkey, data=msg_data)

        client.send(bitjws_msg)

        # publish coin message which should not be received by client
        mdata = {'metal': 'testinium', 'mint': 'testStream.py'}
        msg_data = {'method': 'RESPONSE',
                    'metal': mdata['metal'],
                    'mint': mdata['mint'],
                    'pubhash': pubhash,
                    'headers': {},
                    'model': 'coin',
                    'permissions': ['authenticate'],
                    'id': 1338}

        bitjws_msg = bitjws.sign_serialize(privkey, data=msg_data)

        pika_channel.basic_publish(body=bitjws_msg,
                                   exchange=pikaconfig.EXCHANGE['exchange'],
                                   routing_key='')

        # publish pings to fill queue
        ping_msg_data = {'method': 'ping'}
        bitjws_ping_msg = bitjws.sign_serialize(privkey, data=ping_msg_data)
        for i in range(5):
            client.send(bitjws_ping_msg)

        try:
            data = client_wait_for(client, 'RESPONSE', 'coin', 5)
        except Exception, e:
            self.fail("Unexpected error: %s" % e)
        self.assertIsNone(data)
        client.close()


if __name__ == '__main__':
    test_suite = []
    for cls in (GoodClient, BadClient, MessageLeak):
        test_suite.append(unittest.TestLoader().loadTestsFromTestCase(cls))
    # test_suite = [unittest.TestLoader().loadTestsFromTestCase(GoodClient)]

    for suite in test_suite:
        time.sleep(0.1)
        result = unittest.TextTestRunner(verbosity=2).run(suite)

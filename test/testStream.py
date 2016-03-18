import os
import sys
import json
import time
# import hmac
# import socket
# import hashlib
import unittest
import websocket
import bitjws
# from bravado_bitjws.client import BitJWSSwaggerClient
# from mrest_core.auth.message import prepare_mrest_message, encode_compact_signed_message, decode_signed_message
import pika


# Prepend the parent directory to the sys path.
CLIENT_DIR = ".."
if CLIENT_DIR not in sys.path:
    sys.path.insert(0, CLIENT_DIR)

import pikaconfig

TEST_URL = os.environ.get('WSOCK_URL', 'ws://localhost:8123/websocket')
newcoin = {'metal': 'UB', 'mint': 'Mars global'}

privkey = bitjws.PrivateKey()
pubhash = bitjws.pubkey_to_addr(privkey.pubkey.serialize())

# url = 'http://0.0.0.0:8002/'
# specurl = '%sstatic/swagger.json' % url

# bitjws_client = BitJWSSwaggerClient.from_url(specurl, privkey=privkey)

# username = str(pubhash)[0:8]
# luser = bitjws_client.get_model('User')(username=username)
# bitjws_client.user.addUser(user=luser)

pika_client = pika.BlockingConnection(pika.URLParameters(pikaconfig.BROKER_URL))
pika_channel = pika_client.channel()
pika_channel.exchange_declare(**pikaconfig.EXCHANGE)


def client_wait_for(client, method, model=None, n=20):
    # Assume one of the next n messages will be the
    # one with the desired type on it.
    # print method
    # print model
    while n:
        n -= 1
        msg = client.recv()
        data = json.loads(msg)
        if 'bitjws_jwt' in data:
            try:
                data = bitjws.validate_deserialize(data['bitjws_jwt'])[1]
            except Exception, e:
                print "Error: %s" % e
                return
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

    def tearDown(self):
        self.client.close()


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
        # self.assertIn('schemas', data)
        self.assertIn('now', data)

    def test_ping(self):
        msg = {'bitjws_jwt': bitjws.sign_serialize(privkey, method='ping',
                                                   iat=time.time())}
        self.client.send(json.dumps(msg))
        try:
            data = client_wait_for(self.client, 'pong')
        except Exception, e:
            self.fail("Unexpected error: %s" % e)
        self.assertIn('method', data)
        self.assertEqual(data['method'], 'pong')


    def test_get_coins(self):
        bitjws_jwt = bitjws.sign_serialize(privkey,
                                    method='GET',
                                    pubhash=pubhash,
                                    permissions=['authenticate'],
                                    headers=None,
                                    model='coin',
                                    iat=time.time())
        msg = json.dumps({'bitjws_jwt': bitjws_jwt})
        self.client.send(msg)

        mdata = {'metal': 'testinium', 'mint': 'testStream.py'}
        bitjws_jwt = bitjws.sign_serialize(privkey, method='RESPONSE',
                                           data=mdata, pubhash=pubhash,
                                           headers={},
                                           permissions=['authenticate'],
                                           model='coin')
        msg = json.dumps({'bitjws_jwt': bitjws_jwt})

        pika_channel.basic_publish(body=msg,
                                   exchange=pikaconfig.EXCHANGE['exchange'],
                                   routing_key='')

        try:
            data = client_wait_for(self.client, 'RESPONSE', 'coin')['data']
        except Exception, e:
            self.fail("Unexpected error: %s" % e)
        self.assertEqual(data['metal'], mdata['metal'])
        self.assertEqual(data['mint'], mdata['mint'])

    def test_get_coin_id(self):
        bitjws_jwt = bitjws.sign_serialize(privkey, method='GET', data='',
                                           pubhash=pubhash,
                                           permissions=['authenticate'],
                                           headers=None, model='coin',
                                           id=1337, iat=time.time())
        msg = json.dumps({'bitjws_jwt': bitjws_jwt})
        self.client.send(msg)

        mdata = {'metal': 'testinium', 'mint': 'testStream.py'}
        bitjws_jwt = bitjws.sign_serialize(privkey, method='RESPONSE',
                                           data=mdata, pubhash=pubhash,
                                           headers={},
                                           permissions=['authenticate'],
                                           model='coin', id=1337,
                                           iat=time.time())

        msg = json.dumps({'bitjws_jwt': bitjws_jwt})

        pika_channel.basic_publish(body=msg,
                                   exchange=pikaconfig.EXCHANGE['exchange'],
                                   routing_key='')
#         headers, data = prepare_mrest_message('GET', data="", pubhash=pubhash, privkey=privkey, headers=None, permissions=['authenticate'])
#         packedmess = encode_compact_signed_message('GET', data, headers, 'coin', itemid=1337)
#         self.client.send(json.dumps(packedmess))
#
#         mdata = {'metal': 'testinium', 'mint': 'testStream.py'}
#         heads, pmdata = prepare_mrest_message('RESPONSE', data=mdata, pubhash=pubhash, privkey=privkey,
#                                        headers={}, permissions=['authenticate'])
#         escm = encode_compact_signed_message('RESPONSE', pmdata, heads, 'coin', itemid=1337)
#         mqclient.publish(escm)
        try:
            data = client_wait_for(self.client, 'RESPONSE', 'coin')
        except Exception, e:
            self.fail("Unexpected error: %s" % e)
        self.assertEqual(data['id'], 1337)
        self.assertEqual(data['data']['metal'], mdata['metal'])
        self.assertEqual(data['data']['mint'], mdata['mint'])
#
#
class BadClient(unittest.TestCase, CommonTestMixin):
#
    def setUp(self):
        super(BadClient, self).setup()
#
#     def test_get_bad_format(self):
#         headers, data = prepare_mrest_message('GET', data="", pubhash=pubhash, privkey=privkey, headers=None, permissions=['authenticate'])
#         packedmess = encode_compact_signed_message('GET', data, headers, 'coin')
#         del packedmess['method']
#         self.client.send(json.dumps(packedmess))
#         try:
#             data = client_wait_for(self.client, 'error')
#         except Exception, e:
#             self.fail("Unexpected error: %s" % e)
#         self.assertEqual(data['reason'], 'unknown message')
#
#         packedmess = encode_compact_signed_message('GET', data, headers, 'coin')
#         del packedmess['model']
#         self.client.send(json.dumps(packedmess))
#         try:
#             data = client_wait_for(self.client, 'error')
#         except Exception, e:
#             self.fail("Unexpected error: %s" % e)
#         self.assertEqual(data['reason'], 'unknown message')
#
#     def test_get_coins_bad_sign(self):
#         headers, data = prepare_mrest_message('GET', data="", pubhash=pubhash, privkey=privkey, headers=None, permissions=['authenticate'])
#         headers['x-mrest-sign-0'] = headers['x-mrest-sign-0'][0:-5]
#         packedmess = encode_compact_signed_message('GET', data, headers, 'coin')
#         self.client.send(json.dumps(packedmess))
#         try:
#             data = client_wait_for(self.client, 'error')
#         except Exception, e:
#             self.fail("Unexpected error: %s" % e)
#         self.assertEqual(data['reason'], 'bad credentials')
#
#     def test_subscribe_bad_id(self):
#         # create a new user to create his own coin
#         privkey2 = CKey(os.urandom(64))
#         pubhash2 = str(P2PKHBitcoinAddress.from_pubkey(privkey.pub))
#         keyring2 = [pubhash2]
#
#         mrestClient2 = MRESTClient({'url': 'http://0.0.0.0:8002',
#                                    'PRIV_KEY': privkey2, 'KEYRING': keyring2})
#         mrestClient2.update_server_info(accept_keys=True)
#         mdata = {'metal': 'testinium', 'mint': 'testStream.py'}
#         mrestClient2.post("user", {'pubhash': pubhash2, 'username': pubhash2[0:8]})
#
#         # create a coin owned by the new user
#         coin = mrestClient2.post("coin", mdata)
#
#         # subscribe to the id with the original keys
#         headers, data = prepare_mrest_message('GET', data="", pubhash=pubhash, privkey=privkey, headers=None, permissions=['authenticate'])
#         packedmess = encode_compact_signed_message('GET', data, headers, 'coin', itemid=coin['id'])
#         self.client.send(json.dumps(packedmess))
#
#         mdata = {'metal': 'testinium', 'mint': 'testStream.py'}
#         heads, pmdata = prepare_mrest_message('RESPONSE', data=mdata, pubhash=pubhash, privkey=privkey,
#                                        headers={}, permissions=['authenticate'])
#         escm = encode_compact_signed_message('RESPONSE', pmdata, heads, 'coin', itemid=coin['id'])
#         mqclient.publish(escm)
#
#         # publish pings to fill queue
#         for i in range(0,5):
#             self.client.send(json.dumps({'method': 'ping'}))
#
#         try:
#             data = client_wait_for(self.client, 'RESPONSE', 'coin', 5)
#         except Exception, e:
#             self.fail("Unexpected error: %s" % e)
#         self.assertEqual(data['id'], coin['id'])
#         ddata = decode_signed_message(data)
#         self.assertEqual(ddata['metal'], mdata['metal'])
#         self.assertEqual(ddata['mint'], mdata['mint'])
#
#
class MessageLeak(unittest.TestCase):
    """
#     This test checks whether unknown messages are leaked to the user.
#     In effect this checks how the consumer handles this situation.
#     """
#
#     def test_connect_publish_coin(self):
#         ctm = CommonTestMixin()
#         ctm.setup()
#         client = ctm.client
#         # publish coin message which should not be received by client
#         mdata = {'metal': 'testinium', 'mint': 'testStream.py'}
#         heads, pmdata = prepare_mrest_message('RESPONSE', data=mdata, pubhash=pubhash, privkey=privkey,
#                                        headers={}, permissions=['authenticate'])
#         escm = encode_compact_signed_message('RESPONSE', pmdata, heads, 'coin')
#         mqclient.publish(escm)
#
#         # publish pings to fill queue
#         for i in range(0,5):
#             client.send(json.dumps({'method': 'ping'}))
#
#         try:
#             data = client_wait_for(client, 'RESPONSE', 'coin', 5)
#         except Exception, e:
#             self.fail("Unexpected error: %s" % e)
#         self.assertIsNone(data)
#         client.close()
#
#     def test_connect_publish_coin_id(self):
#         ctm = CommonTestMixin()
#         ctm.setup()
#         client = ctm.client
#
#         # subscribe to a specific coin id
#         headers, data = prepare_mrest_message('GET', data="", pubhash=pubhash, privkey=privkey, headers=None, permissions=['authenticate'])
#         packedmess = encode_compact_signed_message('GET', data, headers, 'coin', itemid=1337)
#         client.send(json.dumps(packedmess))
#
#         # publish coin message which should not be received by client
#         mdata = {'metal': 'testinium', 'mint': 'testStream.py'}
#         heads, pmdata = prepare_mrest_message('RESPONSE', data=mdata, pubhash=pubhash, privkey=privkey,
#                                        headers={}, permissions=['authenticate'])
#         escm = encode_compact_signed_message('RESPONSE', pmdata, heads, 'coin', itemid=1338)
#         mqclient.publish(escm)
#
#         # publish pings to fill queue
#         for i in range(0,5):
#             client.send(json.dumps({'method': 'ping'}))
#
#         try:
#             data = client_wait_for(client, 'RESPONSE', 'coin', 5)
#         except Exception, e:
#             self.fail("Unexpected error: %s" % e)
#         self.assertIsNone(data)
#         client.close()
#
#
if __name__ == '__main__':
    test_suite = []
    for cls in (GoodClient, BadClient, MessageLeak):
        test_suite.append(unittest.TestLoader().loadTestsFromTestCase(cls))
    #test_suite = [unittest.TestLoader().loadTestsFromTestCase(GoodClient)]

    for suite in test_suite:
        time.sleep(0.1)
        result = unittest.TextTestRunner(verbosity=2).run(suite)


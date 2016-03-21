import os
import sys
import json
import pika

import bitjws

configdir = os.environ.get('SOCKJS_MQ_CONFIG_DIR', '../')
if configdir not in sys.path:
    sys.path.append(configdir)

import pikaconfig


pikaClient = pika.BlockingConnection(pika.URLParameters(pikaconfig.BROKER_URL))
pikaChannel = pikaClient.channel()
pikaChannel.exchange_declare(**pikaconfig.EXCHANGE)


def publish(message):
    """
    :param message: a compact signed mrest message
    """
    pikaChannel.basic_publish(body=message,
                              exchange=pikaconfig.EXCHANGE['exchange'],
                              routing_key='')

privkey = bitjws.PrivateKey()
pubhash = bitjws.pubkey_to_addr(privkey.pubkey.serialize())

mdata = {'metal': 'testinium', 'mint': 'publisherDummy.py'}
msg = bitjws.sign_serialize(privkey,
                            metal=mdata['metal'],
                            mint=mdata['mint'],
                            pubhash=pubhash,
                            headers={},
                            permissions=['authenticate'],
                            method='RESPONSE',
                            model='coin')
publish(msg)

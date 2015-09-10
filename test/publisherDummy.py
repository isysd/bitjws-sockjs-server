import os
import sys
import json
import pika

from bitcoin.wallet import CKey, P2PKHBitcoinAddress
from mrest_core.auth.message import *

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
    pikaChannel.basic_publish(body=json.dumps(message),
                              exchange=pikaconfig.EXCHANGE['exchange'],
                              routing_key='')

privkey = CKey(os.urandom(64))
pubhash = str(P2PKHBitcoinAddress.from_pubkey(privkey.pub))

mdata = {'metal': 'testinium', 'mint': 'publisherDummy.py'}
heads, pmdata = prepare_mrest_message('RESPONSE', data=mdata, pubhash=pubhash, privkey=privkey,
                                       headers={}, permissions=['authenticate'])
escm = encode_compact_signed_message('RESPONSE', pmdata, heads, 'coin')
publish(escm)

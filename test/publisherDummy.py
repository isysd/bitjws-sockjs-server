import os
import sys
import json

import pika

configdir = os.environ.get('SOCKJS_MQ_CONFIG_DIR', '../')
if configdir not in sys.path:
    sys.path.append(configdir)

import pikaconfig


pikaClient = pika.BlockingConnection(pika.URLParameters(pikaconfig.BROKER_URL))
pikaChannel = pikaClient.channel()
pikaChannel.exchange_declare(**pikaconfig.EXCHANGE)


def publish(mtype, mdata):
    data = {'type': mtype}
    data.update(mdata)
    pikaChannel.basic_publish(body=json.dumps(data),
                              exchange=pikaconfig.EXCHANGE['exchange'],
                              routing_key='')
publish('sockjsmq', {'hello': 'sockjs'})

import json
import pika

class MQClient():
    def __init__(self, cfg):
        self.client = pika.BlockingConnection(pika.URLParameters(cfg['BROKER_URL']))
        self.pikaChannel = self.client.channel()
        self.pikaChannel.exchange_declare(**cfg['EXCHANGE'])
        self.config = cfg

    def publish(self, data):
        self.pikaChannel.basic_publish(body=data,
                                       exchange=self.config['EXCHANGE']['exchange'],
                                       routing_key='')


import os
import sys
import json
import time

import pika
from pyinotify import WatchManager, Notifier, ProcessEvent

configdir = os.environ.get('SOCKJS_MQ_CONFIG_DIR', '../')
if configdir not in sys.path:
    sys.path.append(configdir)

import pikaconfig


pikaClient = pika.BlockingConnection(pika.URLParameters(pikaconfig.BROKER_URL))
pikaChannel = pikaClient.channel()
pikaChannel.exchange_declare(**pikaconfig.EXCHANGE)

wm = WatchManager()
mask = 4095  # ALL_EVENTS


class PTmp(ProcessEvent):
    def process_default(self, event):
        msg = {'type': 'ticker', 'index': '%s:%.10f' % (str(event), time.time())}
        pikaChannel.basic_publish(body=json.dumps(msg),
                                  exchange=pikaconfig.EXCHANGE['exchange'],
                                  routing_key='')
        print event

notifier = Notifier(wm, PTmp())
wdd = wm.add_watch('/proc', mask, rec=True)
while True:  # loop forever
    try:
        # process the queue of events as explained above
        notifier.process_events()
        if notifier.check_events():
            # read notified events and enqeue them
            notifier.read_events()
        # you can do some tasks here...
    except KeyboardInterrupt:
        # destroy the inotify's instance on this interrupt (stop monitoring)
        notifier.stop()
        break


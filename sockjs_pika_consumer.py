import logging
import pika
from pika import adapters
from collections import defaultdict
from util import setupLogHandlers
import bitjws
import sqlalchemy as sa
import sqlalchemy.orm as orm
from model import User, UserKey, Coin

import pikaconfig


# Messages accepted by this consumer.
KNOWN_MESSAGE_TYPE = set(['sockjsmq', 'auth'])
KNOWN_MESSAGE_FRONT_TYPE = set(['sockjsmq', 'auth', 'pong'])


class AsyncConsumer(object):

    EXCHANGE = pikaconfig.EXCHANGE['exchange']
    EXCHANGE_TYPE = pikaconfig.EXCHANGE['exchange_type']

    def __init__(self, config, ioloop_instance=None):
        """Create a new instance of the consumer class, passing in the config
        with AMQP URL used to connect to RabbitMQ.

        :param config:
        """
        self.config = config
        self._connection = None
        self._channel = None
        self._closing = False
        self._consumer_tag = None
        self._url = config.BROKER_URL

        # An exclusive queue will be automatically created for using
        # with the fanout exchange.
        self._queue = None

        # self.last_tick = None
        self._listener = defaultdict(set)
        self._ioloop_instance = ioloop_instance

        self.schemas = config.SCHEMAS

        logger = logging.getLogger(name='api-stream_consumer')
        for h in setupLogHandlers(fname='API-stream_consumer.log'):
            logger.addHandler(h)
        logger.setLevel(logging.DEBUG)
        logger.info("Consumer created")
        self._log = logger

        # Setup database
        self.engine = sa.create_engine(pikaconfig.SA_ENGINE_URI)
        self.session = orm.sessionmaker(bind=self.engine)()
        User.metadata.create_all(self.engine)
        UserKey.metadata.create_all(self.engine)
        Coin.metadata.create_all(self.engine)

    def connect(self):
        """
        Connect to RabbitMQ and return the connection handle.
        When the connection is established, the on_connection_open method
        will be invoked by pika.

        :rtype: pika.SelectConnection
        """
        self._log.info('Connecting to %s' % self._url)
        return adapters.TornadoConnection(pika.URLParameters(self._url),
                                          self.on_connection_open,
                                          custom_ioloop=self._ioloop_instance)

    def close_connection(self):
        """Close the connection to RabbitMQ."""
        self._log.info('Closing connection')
        self._connection.close()

    def add_on_connection_close_callback(self):
        """
        Add an on close callback that will be invoked by pika
        when RabbitMQ closes the connection to the publisher unexpectedly.
        """
        self._log.debug('Adding connection close callback')
        self._connection.add_on_close_callback(self.on_connection_closed)

    def on_connection_closed(self, connection, reply_code, reply_text):
        """
        Invoked by pika when the connection to RabbitMQ is
        closed unexpectedly.

        :param pika.connection.Connection connection: The closed connection obj
        :param int reply_code: The server provided reply_code if given
        :param str reply_text: The server provided reply_text if given
        """
        self._channel = None
        if self._closing:
            self._connection.ioloop.stop()
        else:
            # XXX Use exponential back-off instead.
            self._log.warning('Connection closed, reopening in 5 seconds: (%s) %s', reply_code, reply_text)
            self._connection.add_timeout(5, self.reconnect)

    def on_connection_open(self, unused_connection):
        """
        Called by pika once the connection to RabbitMQ has
        been established. It passes the handle to the connection object in
        case we need it, but in this case, we'll just mark it unused.

        :type unused_connection: pika.SelectConnection
        """
        self._log.info('Connection opened')
        self.add_on_connection_close_callback()
        self.open_channel()

    def reconnect(self):
        """
        Invoked by the IOLoop timer if the connection is
        closed. See the on_connection_closed method.
        """
        # This is the old connection IOLoop instance, stop its ioloop
        self._connection.ioloop.stop()

        if not self._closing:
            # Create a new connection
            self._connection = self.connect()
            # There is now a new connection, needs a new ioloop to run
            self._connection.ioloop.start()

    def add_on_channel_close_callback(self):
        """
        Tell pika to call the on_channel_closed method if
        RabbitMQ unexpectedly closes the channel.
        """
        self._log.info('Adding channel close callback')
        self._channel.add_on_close_callback(self.on_channel_closed)

    def on_channel_closed(self, channel, reply_code, reply_text):
        """
        Invoked by pika when RabbitMQ unexpectedly closes the channel.
        Channels are usually closed if you attempt to do something that
        violates the protocol, such as re-declare an exchange or queue with
        different parameters. In this case, we'll close the connection
        to shutdown the object.

        :param pika.channel.Channel: The closed channel
        :param int reply_code: The numeric reason the channel was closed
        :param str reply_text: The text reason the channel was closed
        """
        self._log.warning('Channel %i was closed: (%s) %s' % (
            channel, reply_code, reply_text))
        self._connection.close()

    def on_channel_open(self, channel):
        """
        Invoked by pika when the channel has been opened.
        The channel object is passed in so we can make use of it.

        Since the channel is now open, we'll declare the exchange to use.

        :param pika.channel.Channel channel: The channel object
        """
        self._log.debug('Channel opened')
        self._channel = channel
        self.add_on_channel_close_callback()
        self.setup_exchange(self.EXCHANGE)

    def setup_exchange(self, exchange_name):
        """
        Setup the exchange on RabbitMQ by invoking the Exchange.Declare RPC
        command. When it completes, the on_exchange_declareok method will
        be invoked by pika.

        :param str|unicode exchange_name: The name of the exchange to declare
        """
        self._log.debug('Declaring exchange %s' % exchange_name)
        self._channel.exchange_declare(self.on_exchange_declareok,
                                       exchange_name,
                                       self.EXCHANGE_TYPE)

    def on_exchange_declareok(self, unused_frame):
        """
        Invoked by pika when RabbitMQ has finished the Exchange.Declare RPC
        command.

        :param pika.Frame.Method unused_frame: Exchange.DeclareOk response frame
        """
        self._log.debug('Exchange declared')
        self.setup_queue()

    def setup_queue(self):
        """
        Setup the queue on RabbitMQ by invoking the Queue.Declare RPC
        command. When it is complete, the on_queue_declareok method will
        be invoked by pika.
        """
        self._log.debug('Declaring exclusive queue')
        self._channel.queue_declare(self.on_queue_declareok, exclusive=True)

    def on_queue_declareok(self, method_frame):
        """
        Invoked by pika when the Queue.Declare RPC call made in
        setup_queue has completed. In this method we will bind the queue
        and exchange together with the routing key by issuing the Queue.Bind
        RPC command. When this command is complete, the on_bindok method will
        be invoked by pika.

        :param pika.frame.Method method_frame: The Queue.DeclareOk frame
        """
        self._queue = method_frame.method.queue
        self._log.debug('Binding %s to %s' % (self.EXCHANGE, self._queue))
        self._channel.queue_bind(self.on_bindok, queue=self._queue, exchange=self.EXCHANGE)

    def add_on_cancel_callback(self):
        """
        Add a callback that will be invoked if RabbitMQ cancels the consumer
        for some reason. If RabbitMQ does cancel the consumer,
        on_consumer_cancelled will be invoked by pika.
        """
        self._log.debug('Adding consumer cancellation callback')
        self._channel.add_on_cancel_callback(self.on_consumer_cancelled)

    def on_consumer_cancelled(self, method_frame):
        """
        Invoked by pika when RabbitMQ sends a Basic.Cancel for a consumer
        receiving messages.

        :param pika.frame.Method method_frame: The Basic.Cancel frame
        """
        self._log.debug('Consumer was cancelled remotely, shutting down: %r', method_frame)
        if self._channel:
            self._channel.close()

    def acknowledge_message(self, delivery_tag):
        """
        Acknowledge the message delivery from RabbitMQ by sending a
        Basic.Ack RPC method for the delivery tag.

        :param int delivery_tag: The delivery tag from the Basic.Deliver frame
        """
        self._log.debug('Acknowledging message %s' % delivery_tag)
        self._channel.basic_ack(delivery_tag)

    def on_cancelok(self, unused_frame):
        """
        Invoked by pika when RabbitMQ acknowledges the
        cancellation of a consumer. At this point we will close the channel.
        This will invoke the on_channel_closed method once the channel has been
        closed, which will in-turn close the connection.

        :param pika.frame.Method unused_frame: The Basic.CancelOk frame
        """
        self._log.debug('RabbitMQ acknowledged the cancellation of the consumer')
        self.close_channel()

    def stop_consuming(self):
        """
        Tell RabbitMQ that you would like to stop consuming by sending the
        Basic.Cancel RPC command.
        """
        if self._channel:
            self._log.debug('Sending a Basic.Cancel RPC command to RabbitMQ')
            self._channel.basic_cancel(self.on_cancelok, self._consumer_tag)

    def start_consuming(self):
        """
        Set up the consumer by first calling add_on_cancel_callback so that
        the object is notified if RabbitMQ cancels the consumer.
        It then issues the Basic.Consume RPC command which returns the
        consumer tag that is used to uniquely identify the consumer with
        RabbitMQ. We keep the value to use it when we want to cancel
        consuming. The on_message method is passed in as a callback pika
        will invoke when a message is fully received.

        """
        self._log.debug('Issuing consumer related RPC commands')
        self.add_on_cancel_callback()
        self._consumer_tag = self._channel.basic_consume(self.on_message,
                                                         self._queue)

    def on_bindok(self, unused_frame):
        """
        Invoked by pika when the Queue.Bind method has completed. At this
        point we will start consuming messages by calling start_consuming
        which will invoke the needed RPC commands to start the process.

        :param pika.frame.Method unused_frame: The Queue.BindOk response frame
        """
        self._log.debug('Queue bound')
        self.start_consuming()

    def close_channel(self):
        """
        Call to close the channel with RabbitMQ cleanly by issuing the
        Channel.Close RPC command.
        """
        self._log.debug('Closing the channel')
        self._channel.close()

    def open_channel(self):
        """
        Open a new channel with RabbitMQ by issuing the Channel.Open RPC
        command. When RabbitMQ responds that the channel is open, the
        on_channel_open callback will be invoked by pika.
        """
        self._log.debug('Creating a new channel')
        self._connection.channel(on_open_callback=self.on_channel_open)

    def run(self):
        """
        Run the consumer by connecting to RabbitMQ and then
        starting the IOLoop to block and allow the SelectConnection
        to operate.
        """
        self._connection.ioloop.start()

    def stop(self):
        """
        Cleanly shutdown the connection to RabbitMQ by stopping the consumer
        with RabbitMQ. When RabbitMQ confirms the cancellation, on_cancelok
        will be invoked by pika, which will then closing the channel and
        connection. The IOLoop is started again because this method is invoked
        when CTRL-C is pressed raising a KeyboardInterrupt exception. This
        exception stops the IOLoop which needs to be running for pika to
        communicate with RabbitMQ. All of the commands issued prior to starting
        the IOLoop will be buffered but not processed.
        """
        self._log.info('Stopping')
        self._closing = True
        self.stop_consuming()
        self._connection.ioloop.start()
        self._log.info('Stopped')

    def setup(self):
        """Prepare the connection."""
        self._connection = self.connect()

    def on_message(self, unused_channel, basic_deliver, properties, body):
        """
        Invoked by pika when a message is delivered from RabbitMQ. The
        channel is passed for your convenience. The basic_deliver object that
        is passed in carries the exchange, routing key, delivery tag and
        a redelivered flag for the message. The properties passed in is an
        instance of BasicProperties with the message properties and the body
        is the message that was sent.

        The message is delivered according to the settings per listener.

        :param pika.channel.Channel unused_channel: The channel object
        :param pika.Spec.Basic.Deliver: basic_deliver method
        :param pika.Spec.BasicProperties: properties
        :param str|unicode body: The message body
        """
        if basic_deliver and properties:
            self._log.debug('Received message # %s: %s' % (
                basic_deliver.delivery_tag, repr(body)))
            self.acknowledge_message(basic_deliver.delivery_tag)
        else:
            self._log.debug('Received direct message: %r' % body)

        try:
            payload_data = bitjws.validate_deserialize(body)[1]['data']
        except Exception, e:
            self._log.exception(e)
            return
        self._log.info(self._listener)
        for listener, allowed in self._listener.iteritems():
            self._log.info('iterating _listeners\t %s: %s' % (listener, allowed))
            if payload_data['model'] in allowed or ('id' in payload_data and "%s_id_%s" % (payload_data['model'], payload_data['id']) in allowed):
                self._log.info('sending body\t %s' % body)
                listener.send(body)

    def listener_set(self, instance, val):
        if not isinstance(val, str):
            raise TypeError("Expected 'str' got %r" % type(val))
        self._listener[instance] = frozenset([val])

    def listener_add(self, instance, allowed=None):
        self._listener[instance].update(allowed or [])

    def listener_remove(self, instance, disallowed=None):
        self._listener[instance].difference_update(disallowed or [])

    def listener_allowed(self, instance, data):
        """Incomplete/Naive bitjws auth (being developed)"""
        self._log.info("allowed: %s" % data)
        try:
            payload_data = bitjws.validate_deserialize(data)[1]['data']
        except Exception as e:
            print e
            try:
                headers, payload_data = bitjws.multisig_validate_deserialize(data)
            except Exception as e:
                print e
                self._log.info("allowed auth err %s" % e)
                return False
        if payload_data['model'] not in self.schemas:
            return False
        elif 'id' in payload_data:
            if not 'GET' in self.schemas[payload_data['model']]['routes']['/:id']:
                return False
            permissions = self.schemas[payload_data['model']]['routes']['/:id']['GET']
        else:
            if not 'GET' in self.schemas[payload_data['model']]['routes']['/']:
                return False
            permissions = self.schemas[payload_data['model']]['routes']['/']['GET']
        self._log.info("allowed permissions: %s" % permissions)
        if 'pubhash' in permissions:
            if 'pubhash' not in payload_data:
                return False
        return True
        # TODO check if user is authorized for item
        #item = self.sa['session'].query(self.sa_model).all()

    def listener_delete(self, instance):
        self._listener.pop(instance, None)

if __name__ == "__main__":
    consumer = AsyncConsumer(pikaconfig)
    consumer.setup()
    try:
        consumer.run()
    except KeyboardInterrupt:
        consumer.stop()

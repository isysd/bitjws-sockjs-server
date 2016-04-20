import urllib

LOG_DIR = "./"
LOGGER_NAME = 'sockjs-mq-stream_consumer'
LOGGER_FILENAME = 'sockjs-mq-stream_consumer.log'

BROKER_CONNECTION_ATTEMPTS = 3
BROKER_HEARTBEAT = 3600

EXCHANGE = {'exchange': 'sockjsmq', 'exchange_type': 'fanout'}

# import ssl
# BROKER_USE_SSL = {
#     'ca_certs': '/some/place/cacert.pem',
#     'certreqs': ssl.CERT_REQUIRED
# }
BROKER_USE_SSL = None

params = {
    'connection_attempts': BROKER_CONNECTION_ATTEMPTS,
    'heartbeat_interval': BROKER_HEARTBEAT
}
if BROKER_USE_SSL:
    params['ssl_options'] = BROKER_USE_SSL
url = "amqp://guest:guest@127.0.0.1:5672/%2F"  # %%2F is "/" encoded

BROKER_URL = "%s?%s" % (url, urllib.urlencode(params))
CLIENT_BROKER_URL = 'amqp://guest:guest@127.0.0.1:5672//'

SCHEMAS = {'coin': {"description": "model for coin", "title": "CoinSA", "required": ["metal", "mint"], "routes": {"/:id": {"PUT": ["authenticate"], "DELETE": ["authenticate"], "GET": ["authenticate"]}, "/": {"POST": ["authenticate"], "GET": ["authenticate"]}}, "$schema": "http://json-schema.org/draft-04/schema#", "type": "object", "properties": {"metal": {"type": "string", "maxLength": 255}, "mint": {"type": "string", "maxLength": 255}}}}

SA_ENGINE_URI = os.getenv('SA_ENGINE_URI', 'sqlite:////tmp/test.db')

# SockJS Message Queue Server

A SockJS server for forwarding mrest messages from a queue.

## AMQP
The chosen message queue for sockjs-mq-server is [AMQP](http://www.amqp.org/), using the [pika client](http://pika.readthedocs.org/en/latest/).

## mrest

Designed for use in coordination with one or more [mrest http server](https://bitbucket.org/deginner/flask-mrest).

## Running
This project has two processes that need to be run: a sockjs server, and a pika consumer. These can be run like so:

`python sockjs_pika_consumer.py`

`python sockjs_server.py`

It is advised to set up a supervisor for these processes. These are expected to be running before you run the unit tests.
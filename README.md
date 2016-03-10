# SockJS Message Queue Server

A SockJS server for forwarding bitjws messages from a queue. Should not care about contents of the message, which may come from more than one publisher. Should be aware of Users and permissions, and only allow subscription to data that the User has permission to read.

This server is meant to be used in coordination with one or more flask-bitjws server(s) handling HTTP.

![bitjws servers](http://i.imgur.com/4SUa4TA.jpg)

## AMQP
The chosen message queue for sockjs-mq-server is [AMQP](http://www.amqp.org/), using the [pika client](http://pika.readthedocs.org/en/latest/).

## bitjws

Uses [bitjws](https://github.com/deginner/bitjws) message signing for authentication.

## Running
This project has two processes that need to be run: a sockjs server, and a pika consumer. These can be run like so:

`python sockjs_pika_consumer.py`

`python sockjs_server.py`

It is advised to set up a supervisor for these processes. These are expected to be running before you run the unit tests.

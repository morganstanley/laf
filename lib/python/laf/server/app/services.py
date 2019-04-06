"""
Validation and notification
"""
import http.client
import json
import os
import struct
import socket
import logging
from flask import current_app

_LOG = logging.getLogger(__name__)
NOTIFICATION_SOCK = '/tmp/notify.sock'


def validate(req):
    """
    Send the request to validation microservice
    """
    status_code = None
    if 'validation_socket' not in current_app.config:
        return (None, None)
    server_address = current_app.config['validation_socket']
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        sock.connect(server_address)
    except socket.error:
        status_code = http.client.INTERNAL_SERVER_ERROR
        final_req = {'_error': 'Internal server error'}
        return (final_req, status_code)
    json_data = json.dumps(req)
    reqlen = len(json_data)
    sock.sendall(struct.pack('!I{0}s'.format(reqlen),
                             reqlen,
                             json_data.encode()))
    length = sock.recv(4)
    outlen = struct.unpack('!I', length)
    line = sock.recv(outlen[0])
    final_req = json.loads(line.decode())
    sock.close()
    return (final_req, status_code)


def publish(txid, message):
    """
    Publish the message to notification mechanism
    """
    if 'NOTIFICATION_SOCK' not in os.environ:
        return
    server_address = os.environ['NOTIFICATION_SOCK']
    topic = txid
    body = json.dumps(message)
    msg = topic + body

    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        sock.connect(server_address)
    except socket.error:
        pass

    reqlen = len(msg)
    sock.sendall(struct.pack('!I{0}s'.format(reqlen),
                             reqlen,
                             msg.encode()))

    sock.close()

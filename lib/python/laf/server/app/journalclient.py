"""
HTTP client to talk to
laf journal
"""
import http.client
import logging
import os
import requests
import requests_unixsocket  # noqa: E402, pylint: disable=E0401
requests_unixsocket.monkeypatch()

_LOG = logging.getLogger(__name__)


def write(msg):
    """
    Function for writing to journal
    """
    txid = msg['request_id']
    step = msg['step']
    url = 'http+unix://{0}/{1}/{2}'.format(
        os.environ['JOURNAL_SOCK'], txid, step)
    reply = requests.post(url, json=msg,
                          headers={'Accept': 'application/json',
                                   'Content-Type': 'application/json'})
    _LOG.debug(
        '[%s]: journal req reply %s',
        msg['transaction_id'],
        reply.status_code
    )
    _LOG.debug(
        '[%s]: journal req reply content %r',
        msg['transaction_id'],
        reply.content
    )
    return (reply.content, reply.status_code)


def get_status(txid):
    """
    Function to read from journal
    """
    url = 'http+unix://{0}/{1}'.format(
        os.environ['JOURNAL_SOCK'], txid)
    reply = requests.get(url,
                         headers={"Accept": 'application/json',
                                  'Content-Type': 'application/json'})
    _LOG.debug("Request status from journal %r", reply.content)
    if reply.status_code == http.client.PROCESSING:
        resp = 'Task in progress'
    else:
        resp = reply.json()['status']
    return (resp, reply.status_code)

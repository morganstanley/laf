"""
Process the request
by send it to laf workers
"""

import logging
import os
import json
import http.client
# E0401: Unable to import 'zmq'
import zmq  # pylint: disable=E0401
from flask import current_app
from laf.server.app import error
from laf.server.app import authclient

INTERNAL_LONES = ['_status', '_config', '_lones', '_ping']

_LOG = logging.getLogger(__name__)


def process_request(req_obj, version):
    """
    Process the request
    """
    if req_obj.lone in INTERNAL_LONES:
        _process_internal_lones(req_obj)
    else:
        auth_result = None
        if 'authorization_socket' in current_app.config:
            auth_result = authorize(req_obj, version)
        context = zmq.Context()
        socket = context.socket(zmq.REQ)
        socket.identity = (u"client-%d" % (os.getpid())).encode('ascii')
        _LOG.debug(
            '[%s]: frontend url socket is %s',
            req_obj.txid,
            current_app.config['c_socket']
        )
        socket.connect(current_app.config['c_socket'])
        final_req = dict()
        req = {
            'lone': req_obj.lone,
            'verb': req_obj.verb,
            'pk': req_obj.pk,
            'user': req_obj.user,
            'host': req_obj.host,
            'txid': req_obj.txid,
            'rqid': req_obj.rqid,
            'role': req_obj.role,
            'obo': req_obj.obo,
            'cm': req_obj.cm,
            'obj': req_obj.obj,
            'subhandler': req_obj.subhandler,
            'path': req_obj.path,
            'urlvars': req_obj.urlvars,
            'queryvars': req_obj.queryvars,
            'body': req_obj.body
        }
        final_req['request'] = req
        final_req['auth'] = auth_result
        final_req['version'] = version
        try:
            socket.send(json.dumps(final_req).encode())
        except zmq.error.ZMQError:
            _LOG.exception(
                '[%s]: Error in sending request to backend worker',
                req_obj.txid
            )
        else:
            message = socket.recv().decode()
            _LOG.debug(
                '[%s]: Reply got from worker is %r',
                req_obj.txid,
                message
            )
            output = json.loads(message)
    return (output['resp'], output['code'])


def _process_internal_lones(req_obj):
    _LOG.info('internal lone %r', req_obj)


def authorize(req_obj, version):
    """
    authorize request
    """
    auth_res = dict()
    if req_obj.obo is not None:
        obo_auth_result = authclient.obo_authorize(req_obj, version)
        auth_res['oboauth'] = obo_auth_result
    auth_result = authclient.authorize(req_obj, version)
    auth_res['auth'] = auth_result
    _LOG.debug('[%s]: auth result is %r', req_obj.txid, auth_result)
    if not auth_result['authorized']:
        _LOG.info('[%s]: Request not authorized', req_obj.txid)
        raise error.APIError(
            '{0}'.format(auth_result),
            http.client.INTERNAL_SERVER_ERROR,
            req_obj.lone,
            req_obj.verb,
            req_obj.pk,
            req_obj.obj,
            req_obj.user,
            req_obj.host,
            req_obj.txid)
    _LOG.info('[%s]: Request authorized', req_obj.txid)
    return auth_res

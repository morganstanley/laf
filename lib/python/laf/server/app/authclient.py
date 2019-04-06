"""
Auth client
"""

import http.client
import json
import logging
import requests
from flask import current_app  # noqa: E402
import requests_unixsocket  # noqa: E402, pylint: disable=E0401
requests_unixsocket.monkeypatch()
from laf.server.app import error
_LOG = logging.getLogger(__name__)


def authorize(request, version):
    """
    Calling authorize
    """
    user = request.user.split('@')[0]
    verb = request.verb
    lone = request.lone

    req = {'lone': lone,
           'verb': verb,
           'pk': request.pk,
           'user': user,
           'host': request.host,
           'txid': request.txid,
           'role': request.role,
           'obo': request.obo,
           'cm': request.cm,
           'obj': request.obj,
           'urlvars': request.urlvars,
           'queryvars': request.queryvars,
           'body': request.body}
    final_req = {'req': req, 'version': version}
    url = 'http+unix://{0}/{1}/{2}/{3}'.format(
        current_app.config['authorization_socket'], user, lone, verb)
    _LOG.info('auth url is %s', url)
    reply = requests.post(url,
                          json=final_req,
                          headers={"Accept": 'application/json',
                                   'Content-Type': 'application/json'})
    response = json.loads(reply.content.decode())
    if reply.status_code != http.client.OK:
        raise error.APIError(response['message'],
                             reply.status_code,
                             req['lone'],
                             req['verb'],
                             req['pk'],
                             req['obj'],
                             req['user'],
                             req['host'])
    auth_res = dict()
    auth_res['auth'] = response
    return auth_res['auth']


def obo_authorize(request, version):
    """
    Calling on behalf of authorize
    """
    user = request.user.split('@')[0]
    verb = request.verb
    lone = request.lone

    req = {'lone': lone,
           'verb': verb,
           'pk': request.pk,
           'user': user,
           'host': request.host,
           'txid': request.txid,
           'role': request.role,
           'obo': request.obo,
           'cm': request.cm,
           'obj': request.obj}
    final_req = {'req': req, 'version': version}
    url = 'http+unix://{0}/obo/{1}/{2}/{3}'.format(
        current_app.config['authorization_socket'], user, lone, verb)
    reply = requests.post(url,
                          json=final_req,
                          headers={"Accept": 'application/json',
                                   'Content-Type': 'application/json'})
    response = json.loads(reply.content.decode())
    if reply.status_code != http.client.OK:
        raise error.APIError(response['message'],
                             reply.status_code,
                             req['lone'],
                             req['verb'],
                             req['pk'],
                             req['obj'],
                             req['user'],
                             req['host'])
    auth_res = dict()
    auth_res['oboauth'] = response
    return auth_res['oboauth']

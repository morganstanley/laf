"""
Main function to handle requests
"""
import http.client
import logging
import os
from flask import request, current_app
from laf.server.app import services
from laf.server.app import processing
from laf.server.app import journalclient
from laf.server.app import error
from laf.server.app import validator
from laf.server.app import request as LAFRequest

_LOG = logging.getLogger(__name__)


def _build_req_data(inreq,
                    lone):
    """
    Build the request dictionary
    """
    verb = inreq['verb']
    txid = inreq['txid']
    cm = inreq['cm']
    role = inreq['role']
    user = inreq['user']
    remote = inreq['host']
    obo = inreq['obo']
    primarykey = inreq['pk']
    obj = dict()
    if 'path' in inreq:
        inreq['path'].pop('primary_key', None)
        for key, val in inreq['path'].items():
            obj[key] = val
    if 'query' in inreq:
        for key, val in inreq['query'].items():
            obj[key] = val
    if 'body' in inreq:
        obj['body'] = inreq['body']
    req_data = {
        'lone': lone,
        'verb': verb.lower(),
        'pk': primarykey,
        'user': user,
        'host': remote,
        'txid': txid,
        'role': role,
        'obo': obo,
        'cm': cm,
        'obj': obj
    }
    if 'body' in inreq:
        req_data['body'] = inreq['body']
    if 'path' in inreq:
        req_data['urlvars'] = inreq['path']
    if 'query' in inreq:
        req_data['queryvars'] = inreq['query']
    return req_data


def request_validation(req_data):
    """
    Validate request based on Data::Schema
    """
    _LOG.debug('additional validation request is %r', req_data)
    (final_req, status_code) = services.validate(req_data)
    _LOG.debug('request got validated')
    return (final_req, status_code)


def request_handling(req, version):
    """
    Processing of request
    """

    (resp, status_code) = processing.process_request(req, version)
    if status_code not in [http.client.OK,
                           http.client.ACCEPTED,
                           http.client.SERVICE_UNAVAILABLE]:
        raise error.APIError(resp,
                             status_code,
                             req.lone,
                             req.verb,
                             req.pk,
                             req.obj,
                             req.user,
                             req.host,
                             req.txid)
    return (resp, status_code)


def add_pagination_info(url, req_obj, resp, txid):
    """
    For pagination support response will be udpated
    """
    response = dict()
    curr_cursor = ''
    limit = 10
    if '_cursor' in req_obj:
        curr_cursor = req_obj['_cursor']
    if '_limit' in resp:
        limit = resp['_limit']
    if '_elem' in resp:
        response['_elem'] = resp['_elem']
        resp.pop('_elem', None)
        response['_links'] = dict()
        if not curr_cursor:
            response['_links']['_self'] = {
                "href": url
            }
        if curr_cursor:
            response['_links']['_self'] = {
                "href": (
                    url +
                    "?_cursor=" +
                    curr_cursor +
                    "&_limit=" +
                    str(limit)
                )
            }
            response['_links']['_prev'] = {
                "href": (
                    url +
                    "?_cursor=" +
                    curr_cursor +
                    "&_limit=" +
                    str(limit)
                )
            }
        if '_cursor' in resp:
            response['_links']['_next'] = {
                "href": (
                    url +
                    "?_cursor=" +
                    resp['_cursor'] +
                    "&_limit=" +
                    str(limit)
                )
            }
            resp.pop('_cursor', None)
        for key, value in resp.items():
            response[key] = value
    _LOG.debug(
        "[%s]: Final response after pagination is %r",
        txid,
        response
    )
    return response


def handle_route(lone=None,
                 version=None,
                 resp_validator=None,
                 inreq=None):
    """
    Handling route request
    """
    user = request.environ.get('REMOTE_USER')
    host = request.environ.get('REMOTE_HOST')
    _LOG.info('[%s]: Request user and host %s', user, host)
    final_req = _build_req_data(inreq,
                                lone)
    if 'validation_socket' in current_app.config:
        (final_req, status_code) = request_validation(final_req)
        if isinstance(final_req, dict) and '_error' in final_req:
            if status_code is None:
                status_code = http.client.BAD_REQUEST
            raise error.APIError(final_req['_error'],
                                 status_code)
    _LOG.info('final request is %r', final_req)
    req_obj = LAFRequest.Request(**final_req)
    _LOG.info('[%s]: Request validated', req_obj.txid)
    (resp, status_code) = request_handling(req_obj, version)
    if request.method.lower() == 'delete' and status_code == http.client.OK:
        status_code = http.client.NO_CONTENT
    lonepath = '/{0}'.format(final_req['lone'])
    if (
            request.path == lonepath and
            request.method.lower() == 'get' and
            status_code != http.client.SERVICE_UNAVAILABLE and
            version == 'v3'
    ):
        if isinstance(resp, dict) and '_elem' in resp:
            requrl = request.base_url
            if 'url_prefix' in current_app.config['config']:
                urlprefix = current_app.config['config']['url_prefix']
                requrl = '{0}://{1}{2}'.format('http',
                                               urlprefix,
                                               request.path)
            resp = add_pagination_info(requrl,
                                       final_req['obj'],
                                       resp,
                                       req_obj.txid)
        else:
            status_code = http.client.INTERNAL_SERVER_ERROR
            err = "Response should be dictionary"
            raise error.APIError(err,
                                 status_code,
                                 final_req['lone'],
                                 final_req['verb'],
                                 final_req['pk'],
                                 final_req['obj'],
                                 final_req['user'],
                                 final_req['host'],
                                 final_req['txid'])
    validator.validate_response(resp_validator,
                                resp,
                                status_code,
                                req_obj.txid)
    _LOG.info('[%s]: Request Finished', req_obj.txid)
    return (resp, status_code)


def get_status(txid):
    """
    Handling request to get status
    of long running request
    """
    if 'JOURNAL_SOCK' in os.environ:
        (resp, status_code) = journalclient.get_status(txid)
        return (resp, status_code)
    return (None, None)

"""
Main function to handle requests
"""

import http.client
import logging
import os
from flask import make_response, g, current_app, send_file
from laf.server.app import routehandler

_LOG = logging.getLogger(__name__)


def create_response(resp, status_code):
    """
    create response
    """
    if status_code == http.client.ACCEPTED:
        location = resp
        resp_msg = 'Task in progress {0}'.format(location.split('/')[2])
        resp = {'status': resp_msg}
    encoder = g.encoder
    resp = make_response(encoder.encode(resp), status_code)
    if status_code == http.client.ACCEPTED:
        resp.headers['location'] = location
        resp.autocorrect_location_header = False
    resp.headers['Content-Type'] = g.best_accept
    return resp


def general_handler(lone=None,
                    resp_validator=None,
                    inreq=None,
                    version=None):
    """
    View function to handle requests
    """
    (resp, status_code) = routehandler.handle_route(
        lone=lone,
        resp_validator=resp_validator,
        inreq=inreq,
        version=version)
    return create_response(resp, status_code)


def task_status_function(rqid):
    """
    View function to handle request to get status
    of long running request
    """
    _LOG.info('Getting status of request with rqid: %s', rqid)
    (resp, status_code) = routehandler.get_status(rqid)
    encoder = g.encoder
    resp = make_response(encoder.encode(resp), status_code)
    resp.headers['Content-Type'] = g.best_accept
    return resp


def get_api_docs(filename):
    """
    Get the latest openapi 3.0 documentation
    """
    basedir = current_app.config['config']['basedir']
    openapi_dir = os.path.join(basedir, 'apischemas', 'openapi')
    docfile = os.path.join(openapi_dir, filename)
    return send_file(docfile)

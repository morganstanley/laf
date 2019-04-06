"""LAF handling of local Lones requests"""

import http.client
import logging
from laf.server.app import error
from laf.server.app import handler
from laf.server.app import loneutils


__all__ = ['handler']
_LOG = logging.getLogger(__name__)


def local_handler(lone, requests, configdict, luser, lhost):
    """
    handles local requests
    """
    results = []
    (accept, major_version, schemafile) = loneutils.get_accept_header(
        lone, configdict['basedir'])
    # validate request
    final_requests = loneutils.jsonschema_validation(
        configdict['basedir'],
        schemafile,
        accept,
        requests,
        luser,
        lhost)
    for request in final_requests:
        (resp, status_code) = handler.process_req(configdict,
                                                  lone,
                                                  request,
                                                  major_version)
        if status_code not in [http.client.OK, http.client.NO_CONTENT]:
            err_object = error.APIError(resp,
                                        status_code,
                                        request.lone,
                                        request.verb,
                                        request.pk,
                                        request.obj,
                                        luser,
                                        lhost)
            resp = err_object.error_message()
        results.append(resp)
    return results

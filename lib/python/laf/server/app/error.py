"""LAF's error generation"""

import time
import logging
import http.client
from laf.server.app import loneinterface

__all__ = ['gen_error', 'APIError']

_LOG = logging.getLogger(__name__)


class APIError(Exception):
    """
    Exception sub class for
    application related errors
    """
    status_code = http.client.INTERNAL_SERVER_ERROR

    def __init__(self, message,
                 status_code=None,
                 lone=None,
                 verb=None,
                 primaryk=None,
                 obj=None,
                 user=None,
                 host=None):
        super(APIError, self).__init__(self)
        try:
            self.message = message.decode()
        except AttributeError:
            self.message = message
        if status_code is not None:
            self.status_code = status_code
        self.lone = lone
        self.verb = verb
        self.primaryk = primaryk
        self.obj = obj
        self.user = user
        self.host = host

    def error_message(self):
        """
        constructing error message
        """
        if self.verb:
            out = gen_error(self.message,
                            self.lone,
                            self.verb,
                            self.primaryk,
                            self.obj,
                            self.user,
                            self.host)
        else:
            out = {'_error': self.message}
        return out


def gen_error(why, where, verb, primary_k, obj, luser, lhost):
    """
    Generate an error reporting dict
    If we were given a lone instance, use it to print more info
    about the lone's request and configuration
    """

    if isinstance(where, loneinterface.LoneAPI):
        lone = where
        where = '%(env)s/%(family)s/%(lone)s' % {'env': lone.env,
                                                 'family': lone.family,
                                                 'lone': lone.name}
        # XXX: We are reporting the user from the lone's POV.
        #      It could be interesting to report user/obo
        who = lone.user
        host = lone.host
    else:
        where = str(where)
        who = luser
        host = lhost
    when = time.strftime('%Y-%m-%d %H:%M:%S GMT', time.gmtime())
    reply = {'_error': {'why': why,
                        'who': who,
                        'where': where,
                        'when': when,
                        'verb': verb,
                        'pk': primary_k,
                        'in': obj,
                        'from': host}}
    return reply

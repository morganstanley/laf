"""
Vanilla no authentication wsgi plugin
"""
import getpass
import logging
import socket
from werkzeug.local import LocalManager, Local

_LOG = logging.getLogger('__name__')


class NoAuth():
    """
    No authentication
    """
    LOCALS = Local()

    def __init__(self, wrapped, **args):
        """
        """
        self._wrapped = wrapped
        _LOG.debug('Authentication arguments is %r', args)

    def __call__(self, environ, start_response):
        return self.wsgi_app(environ, start_response)

    def wsgi_app(self, environ, start_response):
        """
        WSGI middleware main entry point.
        """
        _LOG.info("Entered noauth plugin")
        environ['REMOTE_USER'] = getpass.getuser()
        environ['REMOTE_HOST'] = socket.gethostname()
        return self._wrapped(environ, start_response)


def make_middleware(wrapped, **args):
    """
    Make middleware wsgi app
    """
    _LOG.debug('Middleware function arguments is %r', args)
    local_manager = LocalManager([NoAuth.LOCALS])
    app = NoAuth(wrapped)
    return local_manager.make_middleware(app)

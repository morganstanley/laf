"""
Main module to start up laf server process
"""
import os
import sys
import logging
from gunicorn.app.base import Application  # noqa: E402, pylint: disable=E0401

from laf.server import createapp

_LOG = logging.getLogger(__name__)


class FlaskApp(Application):
    """
    Load flask application by gunicorn web server
    """

    def __init__(self, app, host, port=None):
        self.app = app
        self.host = host
        self.port = port
        super(FlaskApp, self).__init__()

    def init(self, parser, opts, args):
        """
        Passing options to gunicorn web server
        """
        connection_details = '{0}:{1}'.format(self.host, self.port)
        _LOG.info('connection details is %s', connection_details)
        return {'bind': connection_details}

    def load(self):
        """
        Load flask application
        """
        return self.app


def main(args):
    """
    LAF Server startup entry function
    """

    _LOG.info('input argument basedir: %s, deployment: %s',
              args.basedir, args.deployment)
    if args.journal_sock:
        os.environ['JOURNAL_SOCK'] = args.journal_sock
    app = createapp.create_app(args.basedir, args.client_socket,
                               args.deployment, args.auth_type,
                               args.auth_data,
                               args.validation_sock,
                               args.authorization_sock)
    sys.argv = sys.argv[:1]
    FlaskApp(app, args.host, args.port).run()

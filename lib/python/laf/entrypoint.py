"""
LAF server startup
LAF broker startup
"""

import argparse
import logging
import sys

from laf.server import logger
from laf.server import broker
from laf import laf_server_gunicorn
from laf.server import worker

_LOG = logging.getLogger()


def laf_worker_start():
    """
    LAF Worker start up
    """
    logger.init()
    if len(sys.argv) < 2:
        sys.exit('basedir missing')
    basedir = sys.argv[1]
    _LOG.info("input argument basedir: %s", basedir)
    loneworker = worker.Worker(basedir)
    loneworker.run()


def laf_broker_start():
    """
    LAF Broker start up
    """
    logger.init()
    parser = argparse.ArgumentParser()
    parser.add_argument('-b', '--basedir', required=True,
                        help='basedir of family')
    parser.add_argument('-w', '--workers', required=True,
                        help='number of laf workers')
    parser.add_argument('-d', '--daemon', default=False,
                        help='start workers as daemon')
    parser.add_argument('--client_socket',
                        default="ipc://@frontend.ipc",
                        help='frontend socket for broker')
    parser.add_argument('--worker_socket',
                        default="ipc://@backend.ipc",
                        help='backend socket for broker')
    parser.add_argument('--worker_bin', required=False,
                        default=None,
                        help='worker binary')
    parser.add_argument('--deployment', required=True,
                        help='Deployment of LAF Server')
    parser.add_argument('--notify_sock',
                        help='Notification message socket')
    parser.add_argument('--journal_sock',
                        help='journal process socket')
    args = parser.parse_args()
    _LOG.info("""input argument basedir: %s, workers:%s,
              daemon %s, worker bin:%s, deployment:%s""",
              args.basedir, args.workers, args.daemon,
              args.worker_bin, args.deployment)
    broker.main(args.basedir,
                args.workers, args.daemon,
                args.client_socket,
                args.worker_socket,
                args.worker_bin,
                args.deployment,
                args.notify_sock,
                args.journal_sock)


def laf_server_gunicorn_start():
    """
    LAF server start up
    """
    logger.init()
    parser = argparse.ArgumentParser()
    parser.add_argument('-b', '--basedir', required=True,
                        help='basedir of family')
    parser.add_argument('--deployment', required=True,
                        help='Deployment of LAF Server')
    parser.add_argument('--host', required=True,
                        help='host of LAF Server')
    parser.add_argument('--port', default='8000',
                        help='port of LAF Server')
    parser.add_argument('--client_socket',
                        default="ipc://@frontend.ipc",
                        help='frontend socket for broker')
    parser.add_argument('--auth_type',
                        default='noauth',
                        help='authentication type')
    parser.add_argument('--auth_data',
                        help='authentication data in yaml file')
    parser.add_argument('--journal_sock',
                        help='journal process socket')
    parser.add_argument('--validation_sock',
                        help='Validation process socket')
    parser.add_argument('--authorization_sock',
                        help='Authorization process socket')
    args = parser.parse_args()
    laf_server_gunicorn.main(args)

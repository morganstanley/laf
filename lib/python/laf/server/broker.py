"""
zeromq loadbalancing pattern to
handle laf workers
"""

import os
import signal
import logging
import json
import http.client
import subprocess
# E0401: Unable to import 'zmq'
import zmq  # pylint: disable=E0401
# E0401: Unable to import 'zmq.eventloop.ioloop'
# E0401: Unable to import 'zmq.eventloop.zmqstream'
from zmq.eventloop.ioloop import IOLoop  # pylint: disable=E0401
from zmq.eventloop.zmqstream import ZMQStream  # pylint: disable=E0401
from laf.server import worker

_LOG = logging.getLogger(__name__)


class LRUQueue():
    """LRUQueue class using ZMQStream/IOLoop for event dispatching"""

    __instance = None

    def __new__(cls,
                backend_url=None,
                frontend_url=None,
                basedir=None,
                daemon_flag=None,
                custom_worker_bin=None,
                deployment=None):
        _LOG.debug('lruqueue instance called %s', LRUQueue.__instance)
        if LRUQueue.__instance is None:
            LRUQueue.__instance = super().__new__(cls)

            # Prepare our context and sockets
            context = zmq.Context()
            frontend_socket = context.socket(zmq.ROUTER)
            frontend_socket.bind(frontend_url)
            backend_socket = context.socket(zmq.ROUTER)
            backend_socket.bind(backend_url)
            LRUQueue.__instance.backend_url = backend_url
            LRUQueue.__instance.frontend = ZMQStream(frontend_socket)
            LRUQueue.__instance.backend = ZMQStream(backend_socket)
            LRUQueue.__instance.backend.on_recv(
                LRUQueue.__instance.handle_backend)
            LRUQueue.__instance.frontend.on_recv(
                LRUQueue.__instance.handle_frontend)
            LRUQueue.__instance.workers = dict()
            LRUQueue.__instance.basedir = basedir
            LRUQueue.__instance.daemon = daemon_flag
            LRUQueue.__instance.custom_worker_bin = custom_worker_bin
            LRUQueue.__instance.deployment = deployment
            _LOG.debug('lruqueue instance new done')
        return LRUQueue.__instance

    def handle_backend(self, msg):
        """
        Read input from laf workers and
        pass it to flask clients
        """

        #  Queue worker address for LRU routing
        _LOG.debug('handle backend %r', msg)
        worker_addr, _, client_addr = msg[:3]

        # add worker back to the list of workers
        if client_addr == b"READY":
            self.workers[worker_addr] = None

        # Third frame is READY or else a client reply address
        # If client reply, send rest back to frontend
        if client_addr != b"READY":
            _, reply = msg[3:]
            _LOG.debug('worker reply %r', reply)
            self.frontend.send_multipart([client_addr, b'', reply])

    def handle_frontend(self, msg):
        """
        Get request from laf client and
        send response from laf worker back to
        laf client
        """
        # Client request is [address][empty][request]
        _LOG.debug('handle frontend %r', msg)
        client_addr, _, request = msg
        #  Dequeue and drop the next worker address
        res = {k: v for k, v in self.workers.items() if v is None}
        _LOG.debug('worker count in frontend is %d', len(res))
        for laf_worker, client in self.workers.items():
            if client is None:
                _LOG.debug('current worker is %r',
                           self.workers[laf_worker])
                self.workers[laf_worker] = client_addr
                try:
                    _LOG.debug('sending to worker id %s', laf_worker)
                    self.backend.send_multipart(
                        [laf_worker, b'', client_addr, b'', request])
                except zmq.ZMQError as err:
                    _LOG.exception("Error in worker - %r", err)
                else:
                    return
        _LOG.debug('server busy ; worker list is %r',
                   self.workers)
        _LOG.info('SERVICE UNAVAILABLE')
        message = {'status': 'Try again server busy'}
        result = {'resp': message, 'code': http.client.SERVICE_UNAVAILABLE}
        final_result = json.dumps(result).encode()
        self.frontend.send_multipart([client_addr, b'', final_result])


def signal_handler(signum, _):
    """
    When a laf worker dies, it
    has to be removed from worker list.
    Spawn a new worker process
    """
    if signum == signal.SIGCHLD:
        pwait = os.waitpid(-1, os.WNOHANG)
        _LOG.debug('dead process pid is %r', pwait[0])
        queue = LRUQueue()
        workername = 'Worker-{0}'.format(pwait[0])
        client_addr = queue.workers[workername.encode()]
        if client_addr is not None:
            message = {'status': 'internal server error'}
            result = {'resp': message,
                      'code': http.client.INTERNAL_SERVER_ERROR}
            final_result = json.dumps(result).encode()
            queue.frontend.send_multipart([client_addr, b'', final_result])
        queue.workers.pop(workername.encode())
        _LOG.debug('signal handler worker list is %r',
                   queue.workers)
        if queue.custom_worker_bin:
            custom_worker_env = {
                'WORKER_SOCKET': queue.backend_url,
                'DEPLOYMENT': queue.deployment
            }
            if 'NOTIFICATION_SOCK' in os.environ:
                custom_worker_env['NOTIFICATION_SOCK'] = os.environ[
                    'NOTIFICATION_SOCK']
            if 'JOURNAL_SOCK' in os.envrion:
                custom_worker_env['JOURNAL_SOCK'] = os.environ[
                    'JOURNAL_SOCK']
            subprocess.Popen([queue.custom_worker_bin, queue.basedir],
                             env=queue.customer_worker_env, shell=False)
        else:
            laf_worker = worker.Worker(queue.basedir,
                                       queue.backend_url,
                                       queue.deployment)
            laf_worker.daemon = queue.daemon
            laf_worker.start()


def main(basedir, n_workers, daemon_flag,
         client_socket, worker_socket,
         custom_worker_bin, deployment, notify_socket,
         journal_socket):
    """main method"""
    # create queue with the sockets
    signal.signal(signal.SIGCHLD, signal_handler)
    LRUQueue(worker_socket, client_socket,
             basedir, daemon_flag, custom_worker_bin,
             deployment)
    custom_worker_env = {
        'WORKER_SOCKET': worker_socket,
        'DEPLOYMENT': deployment
    }
    if notify_socket:
        os.environ['NOTIFICATION_SOCK'] = notify_socket
        custom_worker_env['NOTIFICATION_SOCK'] = notify_socket
    if journal_socket:
        os.environ['JOURNAL_SOCK'] = journal_socket
        custom_worker_env['JOURNAL_SOCK'] = journal_socket
    for _ in range(int(n_workers)):
        if custom_worker_bin:
            subprocess.Popen([custom_worker_bin, basedir],
                             env=custom_worker_env,
                             shell=False)
        else:
            laf_worker = worker.Worker(basedir,
                                       worker_socket,
                                       deployment)
            laf_worker.daemon = daemon_flag
            laf_worker.start()

    # start reactor
    IOLoop.instance().start()

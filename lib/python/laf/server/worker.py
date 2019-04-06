"""
LAF worker process
"""

import http.client
import json
import logging
import multiprocessing
import os
import sys
import yaml
# E0401: Unable to import 'zmq'
import zmq  # pylint: disable=E0401

from laf.server.app import config, loneinterface
from laf.server.app import handler
from laf.server.app import request

_LOG = logging.getLogger(__name__)

LAF_LONE_PATH = 'bin'

LONE_MODULE_PATH = 'lib/python'
LAFSVR_CONFIG_FILE = 'etc/laf-server.yml'


class Worker(multiprocessing.Process):
    """ LAF Worker"""
    def __init__(self, basedir, w_socket_url, deployment):
        super().__init__()
        self.laf_worker_config = self.setup_config(basedir, deployment)
        os.environ['LAF_DEPLOYMENT'] = deployment
        self.w_socket_url = w_socket_url

    def run(self):
        #  Wait for next request from client
        _LOG.info('Worker starting with pid %s', os.getpid())
        context = zmq.Context()
        socket = context.socket(zmq.DEALER)
        socket.identity = (u"Worker-%d" % (os.getpid())).encode()
        socket.connect(self.w_socket_url)
        # Tell the broker we are ready for work
        socket.send_multipart([b'', b'READY'])
        long_running = False

        try:
            while True:
                # pylint: disable=E0632
                _, address, _, req = socket.recv_multipart()
                _LOG.debug("%s: %s\n",
                           socket.identity.decode(),
                           req.decode(), end='')
                # actual laf work
                final_req = json.loads(req.decode())
                req_obj = request.Request(**final_req['request'])
                auth_result = final_req['auth']
                lone_obj = self.laf_worker_config['lones'][req_obj.lone]
                req_handler = handler.get_handler(req_obj, lone_obj)
                if handler.is_async_request(req_handler, lone_obj.mode):
                    long_running = True
                    location = '/status/{0}'.format(req_obj.rqid)
                    result = {'resp': location, 'code': http.client.ACCEPTED}
                    final_result = json.dumps(result).encode()
                    socket.send_multipart([b'', address, b'', final_result])
                (resp, code) = handler.process_req(
                    self.laf_worker_config['config'],
                    lone_obj,
                    req_obj,
                    auth_result)
                if not long_running:
                    result = {'resp': resp, 'code': code}
                    final_result = json.dumps(result).encode()
                    socket.send_multipart([b'', address, b'', final_result])
                long_running = False
                socket.send_multipart([b'', b'READY'])
        except zmq.ContextTerminated:
            # context terminated so quit silently
            sys.exit(1)

    def setup_config(self, basedir, deployment):
        """
        Load laf worker config
        """
        worker_config = dict()
        options = {'mode': 'server', 'deployment': deployment}
        laf_config = config.get_lone_cfg(basedir, options)
        loaded_lones = self.load_lones(basedir, laf_config)
        laf_core_base = os.path.dirname(
            os.path.dirname(
                os.path.dirname(
                    os.path.dirname(
                        os.path.abspath(
                            __file__)))))
        worker_config['mode'] = 'server'
        worker_config['config'] = laf_config
        worker_config['basedir'] = laf_core_base
        worker_config['lones'] = loaded_lones
        return worker_config

    def load_lones(self, basedir, laf_config):
        """
        Load laf lones
        """
        srvconfigfile = os.path.join(basedir, LAFSVR_CONFIG_FILE)
        laf_lonepath = os.path.join(basedir, LAF_LONE_PATH)
        laf_lonelib = os.path.join(basedir, LONE_MODULE_PATH)
        sys.path.append(laf_lonepath)
        sys.path.append(laf_lonelib)
        loaded_module = dict()

        # May throw an exception if invalid configfile (i.e. unreadable)
        with open(srvconfigfile) as stream:
            svr_cfg = yaml.load(stream)
            if 'lones' in svr_cfg:
                for lone in svr_cfg['lones']:
                    loaded_module[lone] = loneinterface.load_lone_from_module(
                        lone, laf_config)
                    _LOG.info('loaded lone is %s', lone)
        return loaded_module

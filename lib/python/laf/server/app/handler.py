"""
Handle each laf request
"""
import json
import datetime
import http.client
import logging
import os
import socket
import struct
import subprocess

from laf.server.app import journalclient
from laf.client.loneexception import LoneException

_LOG = logging.getLogger(__name__)

CORE_JOURNAL_VERBS = [
    'insert', 'create', 'delete', 'update', 'remove', 'put', 'post'
]


def get_verb(req_obj):
    """
    Get the request verb
    """
    if req_obj.subhandler and req_obj.subhandler != "default":
        req_verb = req_obj.verb + '_' + req_obj.subhandler
    else:
        req_verb = req_obj.verb
    return req_verb


def get_handler(req_obj, lone_obj):
    """
    Get the handler for
    the verb
    """
    req_verb = get_verb(req_obj)
    handler = lone_obj.__getattribute__(req_verb)
    return handler


def process_req(configdict, lone_obj, req_obj,
                authres=None):
    """
    Process request
    """
    with lone_obj.enter_request(req_obj):
        journal(req_obj, configdict,
                'begin', req_obj.obj, lone_obj)
        if authres is not None:
            if req_obj.obo:
                journal(req_obj, configdict,
                        'authobo', authres['oboauth'], lone_obj)
            journal(req_obj, configdict,
                    'auth', authres['auth'], lone_obj)
        handler = get_handler(req_obj, lone_obj)
        # By now the input is validated and the request authorized
        out = None
        status_code = None
        # Call the lone's handler
        try:
            _LOG.debug('[%s]: Request is v3 in handler', req_obj.txid)
            out = handler(req_obj.pk, **req_obj.obj)
        except LoneException as ex:
            _LOG.exception('[%s]: Lone handling exception', req_obj.txid)
            out, status_code = ex.args  # pylint: disable=E0632
            journal(req_obj, configdict,
                    'abort', out, lone_obj)
            return (out, status_code)
        # W0703: broad-except
        except Exception as err:  # pylint: disable=W0703
            out = repr(err)
            status_code = http.client.INTERNAL_SERVER_ERROR
            journal(req_obj, configdict,
                    'abort', out, lone_obj)
            return (out, status_code)
        else:
            journal(req_obj, configdict,
                    'commit', out, lone_obj)
            if out is None:
                status_code = http.client.NO_CONTENT
            if status_code is None:
                status_code = http.client.OK
            return (out, status_code)


def journaling_allowed(req_obj, lone_obj):
    """
    Check whether journallog
    decorated is uesed
    """
    req_verb = get_verb(req_obj)
    if any(t in req_verb for t in CORE_JOURNAL_VERBS):
        return True
    handler = get_handler(req_obj, lone_obj)
    if hasattr(handler, 'is_journaled'):
        return True
    if is_async_request(handler, lone_obj.mode):
        return True
    return False


def journal(request, configdict, step, payload, lone_obj):
    """
    Write to journal
    """
    if journaling_allowed(request, lone_obj):
        timenow = datetime.datetime.now()
        timestamp = '{0}-{1}-{2} {3}:{4}:{5}'.format(timenow.year,
                                                     timenow.month,
                                                     timenow.day,
                                                     timenow.hour,
                                                     timenow.minute,
                                                     timenow.second)
        msg = {
            'authuser_id': request.user,
            'user_id': request.effective_user,
            'role': request.role,
            'request_id': request.rqid,
            'transaction_id': request.txid,
            'step': step,
            'host': socket.gethostname(),
            'lonefam': configdict['family'] + '/' + configdict['deployment'],
            'lone': configdict['family'] + '/' + request.lone,
            'verb': request.verb,
            'lonepk': request.pk,
            'payload': payload,
            'date': timestamp,
            'cm': request.cm
        }
        _LOG.info('[%s]: journal write %s/%s',
                  request.txid, step, request.rqid)
        if lone_obj.mode == 'lone':
            local_journal_write(configdict, msg)
        else:
            if 'JOURNAL_SOCK' in os.environ:
                journalclient.write(msg)


def local_journal_write(configdict, msg):
    """
    Calling journal cli
    """
    if (
            'primary_journal' not in configdict or
            'secondary_journal' not in configdict or
            'JOURNAL_BINARY' not in os.environ
    ):
        _LOG.critical('Unsaved Journal entry %s:%s',
                      msg['request_id'],
                      msg['step'])
        return
    cmd = os.environ['JOURNAL_BINARY']
    primary = configdict['primary_journal']
    secondary = configdict['secondary_journal']
    adminproid = configdict['remoteid']
    json_data = json.dumps(msg)
    msglen = len(json_data)
    indata = struct.pack('!I{0}s'.format(msglen), msglen, json_data.encode())
    cmdlist = list()
    cmdlist.append(cmd)
    if primary:
        cmdlist.append("--primary")
        cmdlist.append(primary)
    if secondary:
        cmdlist.append("--secondary")
        cmdlist.append(secondary)
    cmdlist.append("--adminproid")
    cmdlist.append(adminproid)
    try:
        subprocess.check_output(cmdlist, input=indata)
    except subprocess.CalledProcessError as ex:
        _LOG.critical('[%s]: Unsaved Journal entry %s:%s',
                      msg['transaction_id'],
                      msg['request_id'],
                      msg['step'])
    # W0703: broad-except
    except Exception as ex:  # pylint: disable=W0703
        _LOG.critical('[%s]: Error in writing to journal %s',
                      msg['transaction_id'],
                      repr(ex))


def is_async_request(handler, mode):
    """
    Check whether request is
    long running
    """

    if mode != 'server':
        return False
    if hasattr(handler, 'is_long_running'):
        return True
    return False

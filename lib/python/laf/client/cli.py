"""LAF command line interface module"""
import functools
import getpass
import inspect
import os
import socket
import sys
import traceback
import yaml

from laf.client import io
from laf.client import cmdline
from laf.server import logger
from laf.server.app import utils
from laf.server.app import config
from laf.server.app import request
from laf.server.app import loneinterface
from laf.server.app import error
from laf.server.app import remotehandler
from laf.server.app import localhandler

__all__ = ['run']


def run(loneclass):
    """
    Run a Lone object from the command line.

    @type lone: C{laf.lone_interface.Lone}
    @param lone: Lone to run from the command line.
    """
    if not inspect.isclass(loneclass) or not issubclass(loneclass,
                                                        loneinterface.LoneAPI):
        raise Exception(
            """Invalid Lone class {0}: not a subclass
            of lone_interface.Lone.""".format(
                repr(loneclass)))

    #  Resolve basedir
    basedir = utils.get_lone_basedir(sys.argv[0])
    luser = getpass.getuser()
    lhost = socket.gethostname()
    #  Parse the command line
    try:
        args = cmdline.get_cmdline(loneclass,
                                   basedir,
                                   luser,
                                   lhost)
    except cmdline.UsageException as ex:
        # Make sure we didn't receive invalid input
        res = error.gen_error(ex.args[0],
                              ex.lonename, ex.verb,
                              ex.pk, ex.obj,
                              lhost, luser)
        print(yaml.dump(res, default_flow_style=False))
        sys.exit(0)
    #  Create the lone's family configuration object
    try:
        configdict = config.get_lone_cfg(basedir,
                                         args['options'])
    # W0703(broad-except)
    except Exception as err:  # pylint: disable=W0703
        res = error.gen_error(err,
                              loneclass.format_name(),
                              args['verb'],
                              args['pk'],
                              args['input'],
                              lhost,
                              luser)
        print(yaml.dump(res, default_flow_style=False))
        sys.exit(0)
    #  Initialize logging
    #  logger.init()

    #  Instanciate the lone
    lone = loneclass(configdict)

    #  Create the request(s)
    try:
        requests = _make_requests(lone,
                                  args['verb'],
                                  args['pk'],
                                  args['input'],
                                  args['options'],
                                  args['path'],
                                  args['body'])
    except TypeError as ex:
        # We have at least one '_error' print and exit
        res = error.gen_error(
            "Error in input:{0}\n{1}".format(repr(ex), traceback.format_exc()),
            lone,
            args['verb'], args['pk'], args['input'], lhost, luser)
        io.yaml_output(sys.stdout, res[0])
        sys.exit(0)

    #  Apply the operations
    if lone.mode == 'client':
        results = remotehandler.remote_handler(
            lone,
            requests,
            configdict, args['options'])
    else:
        logfile = '/tmp/{0}_{1}.log'.format(lone.name, luser)
        logger.init(logfile)
        results = localhandler.local_handler(lone,
                                             requests,
                                             configdict,
                                             luser,
                                             lhost)

    for result in results:
        if result:
            print(yaml.dump(result, default_flow_style=False))


# R0912: too-many-branches), _make_requests]
# pylint: disable=R0912,R0915
def _make_requests(lone, verb, primary_key, objs, options, path, body):
    """
    Massages the input into a list of requests.

    @type lone: C{laf.lone_interface.Lone}
    @param lone: Lone for which we are preparing the input.

    @type pk: string
    @param args: Argument information from the CLI invocation.

    @type args: dict
    @param args: Argument information from the CLI invocation.

    @rtype: list
    @return: List of (pk, obj) tuples
    """
    #  Only one txid per CLI invocation
    if 'LAF-TX-ID' in os.environ:
        txid = os.environ['LAF-TX-ID']
    else:
        txid = request.get_laf_rq_id()

    #  lone command line syntax
    #  If pk is '-' => the pk will be embedded in the yaml input
    #  in the '_id' field
    # R0102: simplifiable-if-statement), _make_requests]
    if primary_key in [None, '-']:  # pylint: disable=R0102
        # See if we can get the pk from the YAML payload
        stub_pk = True
    else:
        stub_pk = False
    if 'obo' in options:
        obo = options['obo']
    else:
        obo = None
    if 'cm' in options:
        cm = options['cm']
    else:
        cm = None
    if 'role' in options:
        role = options['role']
    else:
        role = None
    if objs is None:
        # Input is '--- ~'
        # Is stub_pk True (i.e. pk == '-')?
        if stub_pk:
            req = {'lone': lone.name,
                   'verb': verb,
                   'pk': None,
                   'obj': None,
                   'txid': txid,
                   'obo': obo,
                   'cm': cm,
                   'role': role,
                   'path': None,
                   'body': None}
            return [request.Request(**req)]
        else:
            req = {'lone': lone.name,
                   'verb': verb,
                   'pk': primary_key,
                   'obj': None,
                   'txid': txid,
                   'cm': cm,
                   'role': role,
                   'obo': obo,
                   'path': path,
                   'body': body}
            return [request.Request(**req)]

    elif isinstance(objs, list):
        # Can be either a list of dict or a list of scalars.
        if functools.reduce(
                lambda are_all_dicts, y: are_all_dicts and isinstance(y, dict),
                objs, True):
            # This is a list of dict
            # lone update -
            # ---
            # - _id: a
            #   val:
            #     - a
            #     - b
            # - _id: b
            #   val:
            #     - d
            #     - e
            entries = []
            for entry in objs:
                if stub_pk:
                    if '_id' in entry:
                        req = {'lone': lone.name,
                               'verb': verb,
                               'pk': entry['_id'],
                               'obj': entry,
                               'txid': txid,
                               'obo': obo,
                               'cm': cm,
                               'role': role,
                               'path': path,
                               'body': body}
                        entries.append(request.Request(**req))
                    else:
                        # No '_id' in dict, pk is None
                        req = {'lone': lone.name,
                               'verb': verb,
                               'pk': None,
                               'obj': entry,
                               'txid': txid,
                               'obo': obo,
                               'cm': cm,
                               'role': role,
                               'path': path,
                               'body': body}
                        entries.append(request.Request(**req))
                else:
                    req = {'lone': lone.name,
                           'verb': verb,
                           'pk': primary_key,
                           'obj': entry,
                           'txid': txid,
                           'obo': obo,
                           'cm': cm,
                           'role': role,
                           'path': path,
                           'body': body}
                    entries.append(request.Request(**req))

            return entries
        else:
            entries = []
            for entry in objs:
                if stub_pk:
                    if '_id' in entry:
                        req = {'lone': lone.name,
                               'verb': verb,
                               'pk': entry['_id'],
                               'obj': entry,
                               'txid': txid,
                               'obo': obo,
                               'role': role,
                               'cm': cm,
                               'path': path,
                               'body': body}
                        entries.append(request.Request(**req))
                    else:
                        # No '_id' in dict, pk is None
                        req = {'lone': lone.name,
                               'verb': verb,
                               'pk': None,
                               'obj': entry,
                               'txid': txid,
                               'obo': obo,
                               'cm': cm,
                               'role': role,
                               'path': path,
                               'body': body}
                        entries.append(request.Request(**req))
                else:
                    req = {'lone': lone.name,
                           'verb': verb,
                           'pk': primary_key,
                           'obj': entry,
                           'txid': txid,
                           'obo': obo,
                           'cm': cm,
                           'role': role,
                           'path': path,
                           'body': body}
                    entries.append(request.Request(**req))
            return entries
    else:
        raise TypeError('Can only be list of scalars or list of dict')

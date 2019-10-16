"""Command line management"""

import sys
import os
import traceback
import re
import functools
import argparse
import yaml

from laf.server.app import utils
from laf.server.app import cmdutils

from laf.client import io

__all__ = ['get_cmdline']

HTTP_VERBS = ['get', 'create', 'delete', 'update']


class LoneListAction(argparse.Action):
    """
    Lone list action
    """
    def __call__(self, parser, namespace, values, option_string=None):
        prev_values = getattr(namespace, self.dest)
        if prev_values:
            values = prev_values + values[0].split(',')
        else:
            values = values[0].split(',')
        setattr(namespace, self.dest, values)


class LoneBoolAction(argparse.Action):
    """
    Lone bool action
    """
    def __call__(self, parser, namespace, value, option_string=None):
        setattr(namespace, self.dest, utils.str_to_bool(value))


class LoneArgumentParser(argparse.ArgumentParser):
    """
    Parse arguments of lone
    """
    def __init__(self, *args, **kwargs):
        super(LoneArgumentParser, self).__init__(*args, **kwargs)


def _make_opt_parser(lonename, verb, getopt_config):
    """
    """
    # Merge the default and verb specific configuration
    def _merge_config(xopt, yopt):
        if not xopt:
            return yopt
        elif not yopt:
            return xopt
        else:
            res = dict(xopt)
            res.update(yopt)
            return res

    config = functools.reduce(
        utils.dict_deepmerge,
        [getopt_config.get('default'), getopt_config.get(verb)],
        {})

    loneparse = LoneArgumentParser(prog=lonename, add_help=False)
    for (key, val) in config.items():
        if val.lower() == 'boolean':
            loneparse.add_argument('--%s' % key,
                                   dest=key,
                                   action=LoneBoolAction)
        elif val.lower() == 'list':
            loneparse.add_argument('--%s' % key,
                                   dest=key,
                                   metavar=key.upper(),
                                   nargs='+',
                                   action=LoneListAction)
        elif val.lower() == 'string':
            loneparse.add_argument('--%s' % key, dest=key, metavar=key.upper())
        else:
            raise Exception(
                "Invalid entry in configuration: verb '%s': '%s: %s'" % (verb,
                                                                         key,
                                                                         val))

    return loneparse


def _make_framework_opt_parser(lonename):
    # TODO: Add argument input validation
    loneparse = LoneArgumentParser(
        prog='LAF Framework Level Options: %s' % lonename)
    loneparse.add_argument('--debug', dest='debug', action=LoneBoolAction)
    loneparse.add_argument('--deployment', dest='deployment')
    loneparse.add_argument('--mode', dest='mode')
    loneparse.add_argument('--obo', dest='obo')
    loneparse.add_argument('--role', dest='role')
    loneparse.add_argument('--cm', dest='cm')
    loneparse.add_argument('--status', dest='status')
    loneparse.add_argument('--servers',
                           dest='servers',
                           nargs='+',
                           action=LoneListAction)

    return loneparse


LONE_CONFIG = utils.mkpath('schemas/%(lonename)s.options.yml')


def _get_lone_cli_conf(lonename, rootdir):
    # Go read the Lone's configuration file
    lone_configfile = os.path.join(rootdir,
                                   LONE_CONFIG % {'lonename': lonename})
    if os.path.exists(lone_configfile) and os.path.isfile(lone_configfile):
        f = open(lone_configfile, 'r')
        lone_config = yaml.load(f.read())
    else:
        lone_config = {}

    return lone_config


def _get_framework_opts(lonename, args):
    # Args are the command line argument starting right after the lone
    optparse = _make_framework_opt_parser(lonename)
    fw_opt = []
    while args:
        arg = args.pop(0)
        # We start at the first non-option parameter on the CLI
        if not arg.startswith('--'):  # pylint: disable=R1723
            args.insert(0, arg)
            break
        else:
            if '=' in arg:
                fw_opt.append(arg)
            else:
                fw_opt.append(arg)
                fw_opt.append(args.pop(0))

    (opts, _) = optparse.parse_known_args(args=fw_opt)

    # Transform the result of argparse into a dictionary
    # containing only the specified options
    # XXX: This is not public method of argparse. Might break in the future
    # W0212: (protected-access), _get_framework_opts]
    # pylint: disable=W0212
    fw_opts = dict((k, v) for (k, v) in opts._get_kwargs() if v is not None)

    # Fixup the server entry
    if 'servers' in fw_opts:
        servers = {}
        for server in fw_opts['servers']:
            (proto, param) = server.split(':', 1)
            if 'proto' not in servers:
                servers[proto] = []
            servers[proto].append(param)
        assert len(servers.keys()) == 1, """Multiple server types
        specified on command line"""
        fw_opts['servers'] = servers

    return (fw_opts, args)

#############################################################################
#  Input merging


def _normalize_input(i):
    """
    >>> print _normalize_input(None)
    None
    >>> print _normalize_input([])
    None
    >>> _normalize_input(['a', 'b'])
    [{'_id': 'a'}, {'_id': 'b'}]

    >>> _normalize_input({})
    [{}]
    >>> _normalize_input([{'a': 1}, {'b': 1}])
    [{'a': 1}, {'b': 1}]
    """
    if i is None:
        return None
    elif isinstance(i, list):
        if not i:
            return None
        elif utils.is_not_list_of(i, [list, dict]):
            return [{'_id': x} for x in i]
        else:
            return i
    elif isinstance(i, dict):
        return [i]
    else:
        raise Exception("Invalid input: %s" % (repr(i)))


def _input_multiply(list1, list2):
    """
    >>> _input_multiply([{'a': 1}], [])
    []
    >>> _input_multiply([{'a': 1}, {'a': 2}], [{'b': 1}, {'b': 2}])
    [{'a': 1, 'b': 1}, {'a': 1, 'b': 2}, {'a': 2, 'b': 1}, {'a': 2, 'b': 2}]

    >>> _input_multiply([{'a': {'b': {'c': 3}}}, {'a': {'b': {'d': 4}}}],
    ...                 [{'a': {'b': {'c': 4}}}, {'a': {'b': {'d': 3}}}])
    [{'a': {'b': {'c': 4}}}, {'a': {'b': {'c': 3, 'd': 3}}},
    {'a': {'b': {'c': 4, 'd': 4}}}, {'a': {'b': {'d': 3}}}]
    """
    res = []
    for xitem in list1:
        for yitem in list2:
            res.append(utils.dict_deepmerge(xitem, yitem))
    return res


def _merge_inputs(inputs):
    """
    those are the corner cases
    >>> print _merge_inputs([None, None])
    None
    >>> _merge_inputs([{}, []])
    [{}]
    >>> _merge_inputs([{'a': 1}, None])
    [{'a': 1}]
    >>> _merge_inputs([{'a': 1}, []])
    [{'a': 1}]
    >>> _merge_inputs([[], {'a': 1}])
    [{'a': 1}]
    >>> _merge_inputs([None, ['a']])
    [{'_id': 'a'}]

    >>> _merge_inputs([{'a': 1}, ['a']])
    [{'a': 1, '_id': 'a'}]
    >>> _merge_inputs([['a'], {'a': 1}])
    [{'a': 1, '_id': 'a'}]

    >>> _merge_inputs([{'a': 1}, ['a', 'b']])
    [{'a': 1, '_id': 'a'}, {'a': 1, '_id': 'b'}]
    >>> _merge_inputs([['a', 'b'], {'a': 1}])
    [{'a': 1, '_id': 'a'}, {'a': 1, '_id': 'b'}]

    >>> _merge_inputs([{}, ['a', 'b']])
    [{'_id': 'a'}, {'_id': 'b'}]
    >>> _merge_inputs([{'_id': None}, ['a']])
    [{'_id': 'a'}]

    >>> _merge_inputs([['a', 'b'], ['a', 'c']])
    [{'_id': 'a'}, {'_id': 'c'}, {'_id': 'a'}, {'_id': 'c'}]

    >>> _merge_inputs([[{'a': 1}, {'a': 2}], {'b': 42}])
    [{'a': 1, 'b': 42}, {'a': 2, 'b': 42}]
    >>> _merge_inputs([{'a': 1}, [{'a': 2}, {'b': 42}]])
    [{'a': 2}, {'a': 1, 'b': 42}]
    """
    # Normalize all inputs
    inputs = list(map(_normalize_input, inputs))
    # Filter out None and []
    new_inputs = list(filter(lambda x: x, inputs))

    # Don't try to reduce if there are no inputs
    if new_inputs:
        obj = functools.reduce(_input_multiply, new_inputs)
    else:
        obj = None

    return obj

##########################################################################
#  Input functions


def _get_yaml_from_stdin(lonename, verb, message=None, ask_tty=False):
    """
    """
    try:
        stdin_input = io.read_stdin(message=message, ask_tty=ask_tty)
    except Exception as err:
        raise UsageException(
            lonename,
            'Error parsing STDIN YAML:\n%s' % repr(err),
            verb=verb)
    return stdin_input


def _get_yaml_from_getopt(lonename, verb, lone_config, args):
    """
    """
    # Create a argparse parser for the Lone's verb and parse the command line
    opt_p = _make_opt_parser(lonename, verb, lone_config.get('getopt', {}))
    (opts, rest) = opt_p.parse_known_args(args=args)

    # Transform the result of argparse into a dictionary
    # containing only the specified options
    # XXX: This is not public method of argparse. Might break in the future
    # W0212: (protected-access), _get_framework_opts]
    # pylint: disable=W0212
    getopt_input = dict(
        (k, v) for (k, v) in opts._get_kwargs() if v is not None)
    if not getopt_input:
        getopt_input = None

    return (getopt_input, rest)


def _get_yaml_from_cmdline(args):
    """
    Return YAML string provided on the command line.
    Everything after '---' is assumed to be YAML formatted.
    Handles both ./lone "--- { a: val }" and ./lone --- { a: val } syntax
    """
    rest = []
    for arg in enumerate(args):
        if arg[1].startswith('---'):  # pylint: disable=R1723
            obj = yaml.load(' '.join(args[arg[0]:]))
            break
        else:
            rest.append(arg[1])
    else:
        obj = None

    return (obj, rest)


#########################################################################
PK_PATH_RE = re.compile(r'^(?P<pk>[^\[\]]+)(?:\[(?P<path>[^\[\]]+)\])?$')


def _get_pk_path(pkpath):
    """
    Parse a pk and return the pk and path components of it
    >>> r = _get_pk_path('foo[a]')
    >>> r == {'path': 'a', 'pk': 'foo'}
    True

    >>> r = _get_pk_path('foo[a/b/c]')
    >>> r == {'path': 'a/b/c', 'pk': 'foo'}
    True

    >>> r = _get_pk_path('foo')
    >>> r == {'path': None, 'pk': 'foo'}
    True

    >>> r = _get_pk_path('foo[]')
    >>> r == None
    True
    """
    res = PK_PATH_RE.match(pkpath)
    if not res:
        return None
    return res.groupdict()


# XXX Duplicate of laf.transform code
PK_PATH_SEP = '/'


def _expand_path(path, input_object):
    """
    Wrap an object according to path

    Examples:
    >>> _expand_path("a", 1)
    {'a': 1}
    >>> _expand_path("a/b/c", "prize")
    {'a': {'b': {'c': 'prize'}}}
    """
    waypoint = path.split(PK_PATH_SEP)
    waypoint.reverse()
    return functools.reduce(lambda x, y: {y: x}, waypoint, input_object)

########################################################################


class UsageException(Exception):
    """
    Return a LAF compatible usage exception
    """
    def __init__(self, lonename, reason='usage <verb> <pk>',
                 verb=None, pk=None, obj=None):
        super(UsageException, self).__init__(reason)
        self.lonename = lonename
        self.verb = verb
        self.pk = pk
        self.obj = obj


########################################################################
#  Main function

# W0102: (protected-access), _get_framework_opts]
# R0912(too-many-branches), get_cmdline]
# R0915(too many statements)
# pylint: disable=W0102, R0912, R0915


def get_cmdline(loneclass, rootdir, luser, lhost, args=sys.argv):
    """
    Parse the command line returning the verb, pk and YAML

    @type loneclass: C{laf.lone_interface.Lone}
    @param loneclass: Lone for which we are parsing the command line.

    @rtype: dict
    @return: A dictionary of the 'verb', 'pk' and
    'yaml' found on the command line.
    """
    lonename = loneclass.format_name()
    rest = args[1:]
    # Get framework level options
    (fw_options, rest) = _get_framework_opts(lonename, rest)

    #############################
    ##
    # If --status then len(rest) is not checked and verb = get
    # and immediately return
    ######################

    if 'status' in fw_options:
        return {'verb': 'get',
                'pk': None,
                'input': None,
                'options': fw_options,
                'path': None,
                'body': None}

    if len(rest) < 1:
        # No verb were given on the command line, no need to go further
        raise UsageException(lonename, reason='usage <verb> <pk>')

    # The verb is always the first argument
    verb = rest[0]

    # Help shortcut: get the documentation from the lone
    if verb == 'help':
        import pydoc  # pylint: disable=C0415
        pydoc.getpager()(loneclass.help())
        sys.exit(0)

    # Read provided data from STDIN if it is NOT a TTY
    stdin_input = _get_yaml_from_stdin(lonename, verb)
    # If we received an error on STDIN, do not do input merging
    if isinstance(stdin_input, dict) and '_error' in stdin_input:
        raise UsageException(lonename, reason=stdin_input)

    # Get the lone's CLI configuration
    lone_config = _get_lone_cli_conf(lonename, rootdir)

    # Look in the lone configuration for verbs' default input
    # (this is hardcoded for 'get' and 'delete')
    verbs_default_input = lone_config.get('default_input', {})
    verbs_default_input.update({'get': {}, 'delete': {}})
    if verb not in HTTP_VERBS:
        verbs_default_input.update({verb: {}})
    default_input = verbs_default_input.get(verb, None)
    body = None
    # Get input from getopt style options
    (getopt_input, rest) = _get_yaml_from_getopt(lonename,
                                                 verb,
                                                 lone_config,
                                                 rest)

    # From the rest, extract the YAML given on the command line
    try:
        (yaml_input, rest) = _get_yaml_from_cmdline(rest)
    except Exception as err:
        raise UsageException(
            lonename,
            reason='Error parsing command line YAML:\n%s' % repr(err),
            verb=verb)
    body = yaml_input
    # We are expecting rest to be either 'verb' or 'verb pk'
    if len(rest) == 0:  # pylint: disable=R1720
        # Something wrong happened
        raise UsageException(
            lonename,
            reason='Error parsing command line: %s' % rest,
            verb=verb)
    elif len(rest) == 1:
        pk = None
        path = None
    elif len(rest) == 2:
        # We have a primary key
        pk_info = _get_pk_path(rest[1])
        if not pk_info:
            raise UsageException(
                lonename,
                reason="Unparseable primary key: '%s'" % (rest[1]),
                verb=verb)
        # Apply input expansion pk[some/xpath]
        pk = pk_info['pk']
        path = pk_info['path']
        if path:
            getopt_input = _expand_path(path, getopt_input)
            yaml_input = _expand_path(path, yaml_input)
    else:
        #  We remain with more than two items,
        #  Something went wrong parsing options
        raise UsageException(
            lonename,
            reason="Unrecognized elements on the command line: '{0}'".format(
                rest[2:]),
            verb=verb, pk=rest[1])

    # We now have all input sources covered, merge them all into one
    if verb in HTTP_VERBS:
        try:
            obj = _merge_inputs([default_input,
                                 stdin_input,
                                 getopt_input,
                                 yaml_input])
        except Exception as ex:
            raise UsageException(
                lonename,
                reason='Error merging inputs: {0}\n{1}'.format(
                    repr(ex), traceback.format_exc()),
                verb=verb, pk=pk)
    else:
        if body:
            obj = [body]
        else:
            return {
                'verb': verb,
                'pk': pk,
                'input': None,
                'options': fw_options,
                'path': path,
                'body': body
            }
    # Check now if we need to go into interactive mode
    # If obj is None of if we do not have a pk given on the command line
    if (obj is None) or (pk is '-' and isinstance(  # pylint: disable=R0123
            obj[0], dict) and '_id' not in obj[0]):
        if cmdutils.is_body_required(rootdir,
                                     pk,
                                     verb,
                                     lonename,
                                     path,
                                     obj,
                                     luser,
                                     lhost):
            msg = (
                """Enter YAML input and type """
                """Ctrl-D (i.e. EOF) to submit:\n\n"""
            )
            stdin_input = _get_yaml_from_stdin(
                lonename, verb, message=msg, ask_tty=True)
            # If we received an error on STDIN, do not do input merging
            if isinstance(stdin_input, dict) and '_error' in stdin_input:
                raise UsageException(lonename, reason=stdin_input)

            # Re-merge one more time with the new STDIN input
            obj = _merge_inputs([default_input,
                                 stdin_input,
                                 getopt_input,
                                 yaml_input])

    # TODO: Sanity checks from those ?
    return {
        'verb': verb,
        'pk': pk,
        'input': obj,
        'options': fw_options,
        'path': path,
        'body': body
    }

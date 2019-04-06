"""LAF generic Python utilities"""


import sys
import os
import time
import inspect
import functools

__all__ = ['get_lone_basedir', 'get_callerinfo',
           'insert_lone_module_path', 'str_to_bool']

LONE_MODULE_PATH = 'lib/python%d.%d' % sys.version_info[0:2]


def get_lone_basedir(lone_file):
    """Return the base directory of a lone family from the lone filename"""
    basedir = os.path.realpath(os.path.dirname(os.path.dirname(lone_file)))
    return basedir


def insert_lone_module_path():
    """Return the lone family module directory from the lone filename"""
    (lone_file, _pos) = get_callerinfo(1)
    basedir = get_lone_basedir(lone_file)
    lone_module_path = os.path.join(basedir, LONE_MODULE_PATH)
    sys.path.append(lone_module_path)


def get_callerinfo(level=0):
    """
    Get caller info
    """
    return inspect.getouterframes(inspect.currentframe(),
                                  context=0)[level + 1][1:3]


def mkpath(pathname):
    """
    Converts a unix pathname to os specific pathname.
    """
    if os.path.sep == '/':
        return pathname
    if not pathname:
        return pathname

    # Absolute path. Do this to support AFS pathnames on windows.
    if pathname[0] == '/' and pathname[1] != '/':
        pathname = '/' + pathname

    return os.path.normpath(pathname)


def gmt_time():
    """
    Return the time in the GMT timezone

    @rtype: string
    @return: Time in GMT timezone
    """
    return time.strftime('%Y-%m-%d %H:%M:%S GMT', time.gmtime())


def str_to_bool(value):
    """
    Convert a human readable string into a boolean.
    """
    valuestr = str(value).lower()
    if valuestr in ['1', 'yes', 'enable', 'true']:
        return True
    elif valuestr in ['0', 'no', 'disable', 'false']:
        return False
    else:
        raise Exception("Unable to convert '%s' to boolean" % (repr(value)))


def is_type_of(obj, type_list):
    """
    Check if obj is of one of the type in type_list

    Examples:
    >>> is_type_of('a', [str, unicode])
    True
    >>> is_type_of(['a'], [list])
    True
    >>> is_type_of(['a'], [dict])
    False
    >>> is_type_of(None, [str])
    False
    >>> is_type_of('a', None)
    False
    """
    return functools.reduce(
        lambda res, y: res or isinstance(obj, y),
        type_list, False) if type_list else False


def is_not_list_of(ldata, type_list):
    """
    Check if ldata does not contains any item of any of the types in type_list

    Examples:
    >>> is_not_list_of([['a'], ['b']], [dict])
    True
    >>> is_not_list_of(['a', 'b'], [list, dict])
    True
    >>> is_not_list_of(['a', 'b'], [list, dict, str])
    False
    >>> is_not_list_of(['a', 'b', {}], [list, dict])
    False
    """
    return functools.reduce(
        lambda res, xarg: res and (not is_type_of(xarg, type_list)),
        ldata, True) if ldata else False


def is_list_of(ldata, type_list):
    """
    Check that ldata only contains element of the types in type_list
    >>> is_list_of([], [list])
    False
    >>> is_list_of([], [dict])
    False
    >>> is_list_of(['a', 'b'], [str, unicode])
    True
    """
    return functools.reduce(
        lambda res, xarg: res and is_type_of(xarg, type_list),
        ldata, True) if ldata else False

# R0912: (too-many-branches), dict_deepmerge]


def dict_deepmerge(xarg, yarg):  # pylint: disable=R0912
    """
    >>> print dict_deepmerge(None, None)
    None
    >>> dict_deepmerge({'a': 1}, {})
    {'a': 1}
    >>> dict_deepmerge({'a': 1}, {'b': 2})
    {'a': 1, 'b': 2}
    >>> dict_deepmerge({'a': 1}, {'a': 2})
    {'a': 2}
    >>> dict_deepmerge({'a': {'b': 2, 'c': 3}},
    ...            {'a': {'c': 13, 'd': 4}})
    {'a': {'c': 13, 'b': 2, 'd': 4}}

    >>> dict_deepmerge({'a': [1]}, {'a': [2]})
    {'a': [2]}
    >>> dict_deepmerge({'a': [1]}, {'a': None})
    {'a': None}

    Also note the source dictionaries are untouched:
    >>> l = {'a': {'b': {'c': 3}}}
    >>> r = {'a': {'b': {'d': 4}}}
    >>> dict_deepmerge(l, r)
    {'a': {'b': {'c': 3, 'd': 4}}}
    >>> print l
    {'a': {'b': {'c': 3}}}
    >>> print r
    {'a': {'b': {'d': 4}}}

    And that the results are independent:
    >>> l = {'a': {'b': {'c': 3}}}
    >>> r = {'a': {'d': {'e': 4}}}
    >>> res = dict_deepmerge(l, r)
    >>> res
    {'a': {'b': {'c': 3}, 'd': {'e': 4}}}
    >>> l['a']['b']['c'] = 777
    >>> res
    {'a': {'b': {'c': 3}, 'd': {'e': 4}}}
    """
    if xarg is None:
        return yarg
    if yarg is None:
        return xarg

    if not isinstance(xarg, dict):
        raise ValueError(
            "Invalid argument: must be dictionary: %s" % repr(xarg))
    if not isinstance(yarg, dict):
        raise ValueError(
            "Invalid argument: must be dictionary: %s" % repr(yarg))

    res = {}
    stack = [(res, xarg, yarg)]
    while stack:
        dst, src1, src2 = stack.pop()
        for key in src1:
            if isinstance(src1[key], dict):
                dst[key] = src1[key].copy()
            else:
                dst[key] = src1[key]
        for key in src2:
            if key not in src1:
                # Copy the keys that are not overwritten by src2
                if isinstance(src2[key], dict):
                    dst[key] = src2[key].copy()
                else:
                    dst[key] = src2[key]
            elif isinstance(src1[key], dict) and isinstance(src2[key], dict):
                dst[key] = {}
                stack.append((dst[key], src1[key], src2[key]))
            else:
                if isinstance(src1[key], dict):
                    dst[key] = src2[key].copy()
                else:
                    dst[key] = src2[key]
    return res

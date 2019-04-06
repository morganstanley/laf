"""
Utilities used by jsonschema validation
"""
import http.client
import os
import yaml

from laf.server.app import error


def check_cmconfig(basedir, req_cm, lone, verb,
                   primarykey, obj, user,
                   host, operationid=None):
    """
    Check change management config
    """
    if not operationid:
        operationid = verb
    cmfile = os.path.join(basedir, 'etc/cm-config.yml')
    try:
        with open(cmfile) as outfile:
            try:
                cmconfig = yaml.load(outfile)
                if lone in cmconfig:
                    if operationid in cmconfig[lone]:
                        if not req_cm:
                            msg = (
                                """Please provide a valid change """
                                """management ticket"""
                            )
                            raise error.APIError(
                                msg,
                                http.client.BAD_REQUEST,
                                lone,
                                verb,
                                primarykey,
                                obj,
                                user,
                                host)
            except yaml.YAMLError as _:
                msg = 'Error loading cm-config.yml file'
                raise error.APIError(
                    msg,
                    http.client.BAD_REQUEST,
                    lone,
                    verb,
                    primarykey,
                    obj,
                    user,
                    host)
    except FileNotFoundError as _:
        return


def format_as_index(indices):
    """
    format jsonschema error
    """
    if not indices:
        return ""
    return "[%s]" % "][".join(repr(index) for index in indices)


def get_jsonschema_validation_err(err):
    """
    Convert it to a format
    okay for yaml dump
    """
    schemaerr = {
        "errmsg": err.message,
        "detail": 'Failed validating {0} in schema {1}'.format(
            err.validator,
            format_as_index(list(err.relative_schema_path)[:-1])),
        "schema_path": format_as_index(err.relative_path),
        "schema": err.schema,
    }
    return schemaerr

"""
Validator based on jsonschema
"""

import http.client
import logging
import urllib.parse
import jsonschema
from flask import request, g, current_app
from laf.server.app import error
from laf.server.app import validationutils

_LOG = logging.getLogger(__name__)


def validate_input(req_validator, para_types,
                   lone, verb):
    """
    Validate input parameters and requestbody
    of request
    """
    obj = dict()
    pk = None
    user = request.environ.get('REMOTE_USER')
    host = request.environ.get('REMOTE_ADDR')

    if request.args:
        obj['query'] = dict()
        for key, val in request.args.items():
            try:
                obj['query'][key] = get_queryarg_data(val, para_types[key])
            except (ValueError, TypeError) as _:
                err_msg = 'Invalid query value:{0} for key:{1}'.format(val,
                                                                       key)
                raise error.APIError(err_msg,
                                     http.client.BAD_REQUEST,
                                     lone,
                                     verb,
                                     pk,
                                     obj,
                                     user,
                                     host)
    if request.view_args:
        obj['path'] = dict()
        for key, val in request.view_args.items():
            try:
                obj['path'][key] = get_patharg_data(val, para_types[key])
            except (ValueError, TypeError) as _:
                err_msg = 'Invalid path value:{0} for key:{1}'.format(val,
                                                                      key)
                raise error.APIError(err_msg,
                                     http.client.BAD_REQUEST,
                                     lone,
                                     verb,
                                     pk,
                                     obj,
                                     user,
                                     host)
            if key == 'primary_key':
                pk = obj['path'][key]
    data = None
    if request.data.decode():
        decoder = g.decoder
        data = decoder.decode(request.data)
    if data:
        obj.update({'body': data})
    basedir = current_app.config['config']['basedir']
    req_cm = request.headers.get('LAF-CM', None)
    validationutils.check_cmconfig(basedir, req_cm, lone, verb,
                                   pk, obj, user, host)
    try:
        req_validator.validate(obj)
    except jsonschema.exceptions.ValidationError as err:
        schemaerr = validationutils.get_jsonschema_validation_err(err)
        raise error.APIError(schemaerr,
                             http.client.BAD_REQUEST,
                             lone,
                             verb,
                             pk,
                             obj,
                             user,
                             host)
    obj['pk'] = pk
    obj['verb'] = verb
    obj['user'] = user
    obj['host'] = host
    obj['txid'] = request.headers.get('LAF-TX-ID', None)
    obj['cm'] = request.headers.get('LAF-CM', None)
    obj['role'] = request.headers.get('LAF-ROLE', None)
    obj['obo'] = request.headers.get('LAF-OBO', None)
    return obj


# pylint: disable=R0911
def get_queryarg_data(data, valtype, style='form', explode=False):
    """
    Deserialize data based on style in openapi
    """
    if style == 'form' and not explode:
        if valtype == 'object':
            newdata = data.split(',')
            values = dict(zip(newdata[::2], newdata[1::2]))
            return values
        if valtype == 'array':
            values = [x for x in data.split(',')]
            return values
        if valtype in ['string']:
            return data
        if valtype in ['integer']:
            return int(data)
        if valtype in ['number']:
            return float(data)
        if valtype in ['boolean']:
            return bool(data)
    return data


def get_patharg_data(data, valtype, style='simple', explode=True):
    """
    Deserialize data based on style in openapi
    """
    if style == 'simple' and explode:
        if valtype == 'object':
            data = urllib.parse.unquote(data)
            values = [x.split('=') for x in data.split(',')]
            return {key: val for key, val in values}
        if valtype == 'array':
            data = urllib.parse.unquote(data)
            values = [x for x in data.split(',')]
            return values
        if valtype in ['string']:
            return urllib.parse.unquote(data)
        if valtype in ['integer', 'number']:
            return data
    return data


def validate_response(resp_validator, response, status_code, txid):
    """
    Validate response
    """
    code = str(status_code)
    resp = {
        code: response
    }
    try:
        resp_validator.validate(resp)
    except jsonschema.exceptions.ValidationError as err:
        _LOG.info("[%s]: Response validation error %s", txid, err.message)

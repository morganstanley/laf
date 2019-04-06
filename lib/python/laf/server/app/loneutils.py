"""
LAF utils module
"""

import glob
import json
import importlib
import os
import sys
import yaml
from laf.server.app import routecreator
from laf.server.app import error
from laf.server.app import validationutils

VALIDATION_SOCK = '/tmp/valid.sock'
HTTP_VERBS = ['get', 'create', 'delete', 'update']


def get_http_method(req):
    """
    Get the http method
    """
    if req.verb == 'get' or req.verb == 'delete':
        return req.verb
    if req.verb == 'create':
        if req.pk:
            return 'put'
        return 'post'
    if req.verb == 'update':
        return 'put'
    if req.verb:
        return 'post'
    else:
        return 'get'


def get_accept_header(lone, basedir):
    """
    Get accept header based on latest version of lone
    """
    openapi_dir = os.path.join(basedir, 'apischemas', 'openapi')
    family = '_'.join(lone.family.split('/'))
    pattern = '{0}/vnd.{1}.{2}.v*'.format(openapi_dir, family, lone.name)
    lone_files = glob.glob(pattern)
    if lone_files:
        lone_files.sort(reverse=True)
        lone_file_name = os.path.basename(lone_files[0])
        latest_version = '.'.join(lone_file_name.split('.')[-3::])
        accept = 'application/vnd.{0}.{1}.{2}+json'.format(family,
                                                           lone.name,
                                                           latest_version)
        major_version = lone_file_name.split('.')[-3]
        return (accept, major_version, lone_files[0])
    return (None, None, None)


def get_path_for_request(req, rsrcpara_types, luser, lhost):
    """
    Create the path format
    """
    urlvars = dict()
    reqpath = '/{0}'.format(req.lone)
    if req.verb not in HTTP_VERBS:
        reqpath = reqpath + ':' + req.verb
        return (reqpath, urlvars)
    if req.pk:
        reqpath = reqpath + '/{primary_key}'
        urlvars['primary_key'] = req.pk
    if req.verb in HTTP_VERBS and req.pk:  # pylint: disable=R1702
        if req.path:
            givenpath = req.path.lstrip('/')
            pathsvar = givenpath.split('/')
            pathpart = None
            flag = False
            for pathvar in pathsvar:
                if pathvar in rsrcpara_types:
                    reqpath = reqpath + '/' + pathvar
                    pathpart = pathvar
                    flag = False
                else:
                    if pathpart is None:
                        msg = 'Wrong request format {0}'.format(pathpart)
                        res = error.gen_error(msg,
                                              req.lone, req.verb,
                                              req.pk, req.obj,
                                              luser, lhost)
                        print(yaml.dump(res, default_flow_style=False))
                        sys.exit(1)
                    if '=' in pathvar:
                        reqpath = reqpath + '/{' + pathpart + '_keys}'
                        urlvars[pathpart + '_keys'] = pathvar
                        flag = True
                    else:
                        if flag is False:
                            reqpath = reqpath + '/{' + pathpart + '}'
                            urlvars[pathpart] = pathvar
                        else:
                            urlvars[pathpart + '_keys'] = (
                                urlvars[pathpart + '_keys'] + '/' + pathvar
                            )
    return (reqpath, urlvars)


def build_req_data(req, family):
    """
    Build request data
    """
    req_data = [{
        'family': family,
        'lone': req.lone,
        'command': req.verb,
        'pk': req.pk,
        'user': req.user,
        'host': req.host,
        'txid': req.txid,
        'role': req.role,
        'obo': req.obo,
        'cm': req.cm,
        'obj': req.obj
    }]
    return req_data


# pylint: disable=R0915
def jsonschema_validation(laf_family_base, schemafile, mimetype,
                          requests, luser, lhost):
    """
    Validate using json schema
    """
    spec = importlib.util.find_spec('jsonschema')
    jsonschema = spec.loader.load_module()
    with open(schemafile) as infile:
        spec = json.load(infile)
    base = "file://{0}/apischemas/openapi/".format(laf_family_base)
    resolver = jsonschema.RefResolver(base_uri=base, referrer=spec)
    rsrcpara_types = list(spec['components']['schemas'].keys())
    results = []
    for req in requests:
        (request_path, urlvars) = get_path_for_request(req,
                                                       rsrcpara_types,
                                                       luser,
                                                       lhost)
        if request_path not in list(spec['paths'].keys()):
            msg = 'Wrong command request format {0}'.format(request_path)
            res = error.gen_error(msg,
                                  req.lone, req.verb,
                                  req.pk, req.obj,
                                  luser, lhost)
            print(yaml.dump(res, default_flow_style=False))
            sys.exit(1)
        path_spec = spec['paths'][request_path]
        method = get_http_method(req)
        action = path_spec[method]
        operationid = action['operationId']
        kwargs = dict()
        kwargs = routecreator.generate_kwargs(action, resolver)
        schema_obj = routecreator.generate_schema_obj(mimetype,
                                                      kwargs['parameters'],
                                                      kwargs['requestbody'])
        req_validator = jsonschema.Draft4Validator(schema_obj,
                                                   resolver=resolver)
        para_types = dict()
        for para_name, para_value in kwargs['parameters']['path'].items():
            (_, ptype) = routecreator.get_parameter_types(
                para_value, resolver)
            para_types[para_name] = ptype
        for para_name, para_value in kwargs['parameters']['query'].items():
            (_, ptype) = routecreator.get_parameter_types(
                para_value, resolver)
            para_types[para_name] = ptype

        obj = dict()
        final_obj = dict()
        if method == 'get' and not req.pk:
            obj['query'] = dict()
            for key, val in req.obj.items():
                obj['query'][key] = get_queryarg_data(val, para_types[key])
                final_obj[key] = obj['query'][key]
        if urlvars:
            obj['path'] = dict()
            for key, val in urlvars.items():
                obj['path'][key] = get_patharg_data(val, para_types[key])
                final_obj[key] = obj['path'][key]
        if req.body and method != 'get':
            obj.update({'body': req.body})
            final_obj['body'] = req.body
        try:
            validationutils.check_cmconfig(laf_family_base, req.cm,
                                           req.lone, req.verb, req.pk,
                                           req.obj, luser, lhost,
                                           operationid)
        except error.APIError as err:
            res = err.error_message()
            print(yaml.dump(res, default_flow_style=False))
            sys.exit(1)
        try:
            req_validator.validate(obj)
        except jsonschema.exceptions.ValidationError as err:
            schemaerr = validationutils.get_jsonschema_validation_err(err)
            res = error.gen_error(schemaerr,
                                  req.lone, req.verb,
                                  req.pk, req.obj,
                                  luser, lhost)
            print(yaml.dump(res, default_flow_style=False))
            sys.exit(1)
        final_obj.pop('primary_key', None)
        req.obj = final_obj
        req.verb = operationid
        req.user = luser
        req.host = lhost
        results.append(req)
    return results


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
            values = [x.split('=') for x in data.split(',')]
            return {key: val for key, val in values}
        if valtype == 'array':
            values = [x for x in data.split(',')]
            return values
        if valtype in ['string', 'integer', 'number']:
            return data
    return data

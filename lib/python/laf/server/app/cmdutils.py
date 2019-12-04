"""
LAF utils module
"""
import glob
import json
import os
import sys
import yaml
from laf.server.app import config
from laf.server.app import error

HTTP_VERBS = ['get', 'create', 'delete', 'update']


def get_schemafile(lone, lonefamily, basedir):
    """
    Get schemafile on latest version of lone
    """
    openapi_dir = os.path.join(basedir, 'apischemas', 'openapi')
    family = '_'.join(lonefamily.split('/'))
    pattern = '{0}/vnd.{1}.{2}.v*'.format(openapi_dir, family, lone)
    lone_files = glob.glob(pattern)
    lone_files.sort(reverse=True)
    return lone_files[0]


def get_http_method(reqpk, reqverb):
    """
    Get the http method
    """
    if reqverb in ['get', 'delete']:
        return reqverb
    if reqverb == 'create':
        if reqpk:
            return 'put'
        return 'post'
    if reqverb == 'update':
        return 'put'
    if reqverb:
        return 'post'
    else:
        return 'get'


def get_path_for_request(reqlone,
                         reqverb,
                         reqpk,
                         reqobj,
                         reqpath,
                         rsrcpara_types,
                         luser, lhost):
    """
    Create the path format
    """
    urlvars = dict()
    requestpath = '/{0}'.format(reqlone)
    if reqpk:
        requestpath = requestpath + '/{primary_key}'
        urlvars['primary_key'] = reqpk
    if reqverb in HTTP_VERBS and reqpk:  # pylint: disable=R1702
        if reqpath:
            givenpath = reqpath.lstrip('/')
            pathsvar = givenpath.split('/')
            pathpart = None
            flag = False
            for pathvar in pathsvar:
                if pathvar in rsrcpara_types:
                    requestpath = requestpath + '/' + pathvar
                    pathpart = pathvar
                    flag = False
                else:
                    if pathpart is None:
                        msg = 'Wrong request format {0}'.format(pathpart)
                        res = error.gen_error(msg,
                                              reqlone, reqverb,
                                              reqpk, reqobj,
                                              luser, lhost)
                        print(yaml.dump(res, default_flow_style=False))
                        sys.exit(1)
                    if '=' in pathvar:
                        requestpath = requestpath + '/{' + pathpart + '_keys}'
                        urlvars[pathpart + '_keys'] = pathvar
                        flag = True
                    else:
                        if flag is False:
                            requestpath = requestpath + '/{' + pathpart + '}'
                            urlvars[pathpart] = pathvar
                        else:
                            urlvars[pathpart + '_keys'] = (
                                urlvars[pathpart + '_keys'] + '/' + pathvar
                            )
    return (requestpath, urlvars)


def is_body_required(basedir,
                     reqpk,
                     reqverb,
                     reqlone,
                     reqpath,
                     reqobj,
                     luser, lhost):
    """
    Check whether this request require body
    """
    lonefamily = config.get_laf_family(basedir)
    schemafile = get_schemafile(reqlone, lonefamily, basedir)
    openapi_dir = os.path.dirname(schemafile)
    if not os.path.isdir(openapi_dir) or (not os.listdir(openapi_dir)):
        return True
    with open(schemafile) as infile:
        spec = json.load(infile)
    rsrcpara_types = list(spec['components']['schemas'].keys())
    (request_path, _) = get_path_for_request(reqlone,
                                             reqverb,
                                             reqpk,
                                             reqobj,
                                             reqpath,
                                             rsrcpara_types,
                                             luser,
                                             lhost)
    if request_path not in list(spec['paths'].keys()):
        msg = 'Wrong command request format {0}'.format(request_path)
        res = error.gen_error(msg,
                              reqlone, reqverb,
                              reqpk, reqobj,
                              luser, lhost)
        print(yaml.dump(res, default_flow_style=False))
        sys.exit(1)
    path_spec = spec['paths'][request_path]
    method = get_http_method(reqpk, reqverb)
    action = path_spec[method]
    if "requestBody" in action:
        if 'required' in action["requestBody"]:
            if action["requestBody"]['required'] is True:
                return True
    return False

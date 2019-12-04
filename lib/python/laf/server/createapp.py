"""
Creating laf client wsgi app
"""

import copy
import glob
import json
import http.client
import os
import logging
import re
from flask import Flask, g, make_response, Blueprint, request
# E0401: Unable to import 'flask_cors'
from flask_cors import CORS  # pylint: disable=E0401
import flask_accept  # pylint: disable=E0401
# E0401: Unable to import 'flask_swagger_ui'
from flask_swagger_ui import get_swaggerui_blueprint  # pylint: disable=E0401
from jsonschema import Draft4Validator, RefResolver
import yaml
from laf.server.app import config
from laf.server.app.error import APIError
from laf.server.app import generalhandler
from laf.server.app import routecreator
from laf.server.app import types
from laf.server.app import error
from laf.server.app import validator
from laf.server.app import wsgiplugin
# W0611: unused-import
import laf.server.gunicornpatch  # pylint: disable=W0611
_LOG = logging.getLogger(__name__)
LAFSVR_CONFIG_FILE = 'etc/laf-server.yml'
APP = Flask(__name__)
CORS(APP)
MIME_REGEX = re.compile(r'^application/(.+)\+(yaml|json)$')
DEFAULT_MIME_TYPES = ['application/yaml', 'application/json']


def get_latest_schema(basedir, family, lone):
    """
    Get the latest openapi spec for lone
    """
    openapi_dir = os.path.join(basedir, 'apischemas', 'openapi')
    family = '_'.join(family.split('/'))
    pattern = '{0}/vnd.{1}.{2}.v*'.format(openapi_dir, family, lone)
    lone_files = glob.glob(pattern)
    lone_files.sort(reverse=True)
    lone_file_name = os.path.basename(lone_files[0])
    return lone_file_name


def lone_latest_version(basedir, family, lone):
    """
    Get the latest version of lone
    """
    lone_file_name = get_latest_schema(basedir, family, lone)
    latest_version = '.'.join(lone_file_name.split('.')[-3::])
    return latest_version


def setup_config(app, basedir, c_socket, deployment,
                 validation_socket,
                 authorization_socket):
    """
    Set laf client config
    """
    options = {'mode': 'server', 'deployment': deployment}
    laf_config = config.get_lone_cfg(basedir, options)
    laf_core_base = os.path.dirname(os.path.dirname(
        os.path.dirname(
            os.path.dirname(
                os.path.abspath(__file__)))))
    with app.app_context():
        app.config['mode'] = 'server'
        app.config['config'] = laf_config
        app.config['basedir'] = laf_core_base
        if authorization_socket:
            authorize_sock = authorization_socket.replace('/', '%2F')
            app.config['authorization_socket'] = authorize_sock
        if validation_socket:
            app.config['validation_socket'] = validation_socket
        app.config['c_socket'] = c_socket
        app.config['deployment'] = deployment
    return laf_config


def setup_app(app, basedir,
              client_socket, deployment,
              validation_socket,
              authorization_socket):
    """
    set up laf client
    """
    return setup_config(app, basedir,
                        client_socket, deployment,
                        validation_socket,
                        authorization_socket)


def create_register_blueprint(lone_bprint,
                              spec,
                              version,
                              latest_version,
                              major_version,
                              path,
                              lone,
                              mime_types,
                              resolver):
    """
    Register blueprint for major version v3
    """
    path_spec = copy.deepcopy(spec['paths'][path])
    _LOG.debug("Path is %s", path)
    for method, action in path_spec.items():
        _LOG.debug("method is %s ", method)
        path_route = routecreator.generate_path_route(path,
                                                      action['parameters'],
                                                      resolver)
        _LOG.debug("path route is %s", path_route)
        operationid = action['operationId']
        _LOG.debug("operation id is %s", operationid)
        kwargs = dict()
        kwargs = routecreator.generate_kwargs(action, resolver)
        _LOG.debug('kwargs after generation %r', kwargs)
        schema_obj = routecreator.generate_schema_obj(mime_types[0],
                                                      kwargs['parameters'],
                                                      kwargs['requestbody'])
        _LOG.debug('schema obj is %r', schema_obj)
        resp_obj = routecreator.generate_resp_obj(mime_types[0],
                                                  kwargs['responses'])
        _LOG.debug('resp obj is %r', resp_obj)
        req_validator = Draft4Validator(schema_obj,
                                        resolver=resolver)
        resp_validator = Draft4Validator(resp_obj,
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
        _LOG.debug("para types is %r", para_types)
        add_the_rule(lone_bprint,
                     path_route,
                     method,
                     operationid=operationid,
                     version=version,
                     latest_version=latest_version,
                     major_version=major_version,
                     lone=lone,
                     mime_types=mime_types,
                     req_validator=req_validator,
                     resp_validator=resp_validator,
                     para_types=para_types)


def add_the_rule(lone_bprint,
                 path_route,
                 method,
                 operationid=None,
                 version=None,
                 latest_version=None,
                 major_version=None,
                 lone=None,
                 mime_types=None,
                 req_validator=None,
                 resp_validator=None,
                 para_types=None):
    """
    Based on openapi schema add new url rule to blueprint
    """

    # W0613: Unused argument
    def handler_view_func(*a, **kw):  # pylint: disable=W0613
        """
        v3 view function
        """
        return generalhandler.general_handler(
            inreq=validator.validate_input(req_validator,
                                           para_types,
                                           lone,
                                           operationid),
            lone=lone,
            resp_validator=resp_validator,
            version=major_version)
    key = '{0}##{1}'.format(path_route, method.lower())
    if key in lone_bprint[lone] and lone_bprint[lone][key]:
        _LOG.info(
            "Add accept types %r for existing route path:%s and method %s",
            mime_types, path_route, method
        )
        acceptor = lone_bprint[lone][key]
        acceptor.support(*mime_types)(handler_view_func)
        if version == latest_version and method.lower() == 'get':
            acceptor.support('*/*')(handler_view_func)
    else:
        acceptor = flask_accept.accept(*mime_types)(handler_view_func)
        if version == latest_version and method.lower() == 'get':
            acceptor.support('*/*')(handler_view_func)
        lone_bprint[lone][key] = acceptor
        _LOG.info(
            "Add accept type %r for new route path:%s and method %s",
            mime_types, path_route, method
        )
        blue_print = lone_bprint[lone]['blueprint']
        blue_print.add_url_rule(path_route,
                                strict_slashes=False,
                                methods=[method],
                                endpoint=operationid,
                                view_func=acceptor)


def get_mime_types(responses):
    """
    List of allowed mime types
    """
    mimetypes = list()
    if 'Ok_all' in responses and 'content' in responses['Ok_all']:
        for mime in responses['Ok_all']['content'].keys():
            mimetypes.append(mime)
    if 'Ok' in responses and 'content' in responses['Ok']:
        for mime in responses['Ok']['content'].keys():
            mimetypes.append(mime)
    if 'Created' in responses and 'content' in responses['Created']:
        for mime in responses['Created']['content'].keys():
            mimetypes.append(mime)
    return list(set(mimetypes))


def add_lone_path(apifile, family, major_version,
                  lone_bprint, version, basedir, lone):
    """
    Add routes
    """
    with open(apifile) as infile:
        spec = json.load(infile)
        _LOG.info("Loading spec file - %s ", apifile)
        validpaths = list(spec['paths'].keys())
        _LOG.debug("validpaths in this lone is %r", validpaths)
        allowed_mime_types = get_mime_types(spec['components']['responses'])
        latest_version = lone_latest_version(basedir, family, lone)
        _LOG.debug("creating routes for %s", lone)
        base = "file://{0}/apischemas/openapi/".format(basedir)
        resolver = RefResolver(base_uri=base,
                               referrer=spec)
        for path in validpaths:
            _LOG.debug("Path in validapath is %r", path)
            create_register_blueprint(lone_bprint,
                                      spec,
                                      version,
                                      latest_version,
                                      major_version,
                                      path,
                                      lone,
                                      allowed_mime_types,
                                      resolver)


def register_api_docs(lone, basedir, family):
    """
    Register blueprint for each lone apis docs
    """
    filename = get_latest_schema(basedir, family, lone)
    swagger_url = '/{0}/_docs'.format(lone)
    api_url = '/{0}/_static/{1}'.format(lone, filename)
    lone_url = '/{0}/_static/<string:filename>'.format(lone)
    family_name = '_'.join(family.split('/'))
    lone_name = '{0} {1} resource'.format(family_name, lone)
    lonedocs_name = '{0}_{1}'.format(family_name, lone)
    swaggerui_blueprint = get_swaggerui_blueprint(
        swagger_url,
        api_url,
        config={
            'app_name': lone_name
        },
        blueprint_name=lonedocs_name
    )
    docs_name = '{0}_{1}_{2}'.format(family_name, lone, 'docs')
    APP.register_blueprint(swaggerui_blueprint, url_prefix=swagger_url)

    docs_blue = Blueprint(docs_name, __name__)
    docs_blue.add_url_rule(lone_url,
                           strict_slashes=False,
                           methods=['GET'],
                           endpoint=docs_name,
                           view_func=generalhandler.get_api_docs)
    APP.register_blueprint(docs_blue)


def create_app(basedir, client_socket,
               deployment,
               auth_type,
               auth_data,
               validation_socket,
               authorization_socket):
    """
    creating a flask app
    """
    authentication_plugin = wsgiplugin.get_authentication_plugin(auth_type)
    authentication_data = dict()
    if auth_data:
        with open(auth_data) as stream:
            authentication_data = yaml.load(stream)
    APP.wsgi_app = authentication_plugin.make_middleware(
        APP.wsgi_app, **authentication_data)

    lafcfg = setup_app(APP, basedir,
                       client_socket, deployment,
                       validation_socket, authorization_socket)
    openapi_dir = os.path.join(basedir, 'apischemas', 'openapi')
    lone_bprint = dict()
    for openapi_file in os.listdir(openapi_dir):
        apifile = os.path.join(openapi_dir, openapi_file)
        if os.path.isfile(apifile):
            version = '.'.join(openapi_file.split('.')[-3::])
            major_version = openapi_file.split('.')[-3]
            lone = openapi_file.split('.')[-4]
            if lone not in lone_bprint:
                lone_bprint[lone] = {
                    'blueprint': Blueprint(lone, __name__)
                }
            add_lone_path(apifile, lafcfg['family'], major_version,
                          lone_bprint, version, basedir, lone)
    for lonename, loneval in lone_bprint.items():
        if lone_bprint[lonename]['blueprint'] is not None:
            APP.register_blueprint(loneval['blueprint'])
    # register api doc paths
    srvconfigfile = os.path.join(basedir, LAFSVR_CONFIG_FILE)
    with open(srvconfigfile) as stream:
        svr_cfg = yaml.load(stream)
        if 'lones' in svr_cfg:
            for lone in svr_cfg['lones']:
                register_api_docs(lone,
                                  lafcfg['basedir'],
                                  lafcfg['family'])

    status_blue = Blueprint('status_blueprint', __name__)
    status_blue.add_url_rule('/<uuid:rqid>',
                             strict_slashes=False,
                             methods=['GET'],
                             endpoint='status',
                             view_func=generalhandler.task_status_function)
    prefix_status = '/status'
    APP.register_blueprint(status_blue, url_prefix=prefix_status)

    return APP


def setup_mime(mime_type):
    """
    set up mime
    """
    return types.TypesObj.factory(mime_type)


@APP.errorhandler(APIError)
def handle_api_error(err):
    """
    Error handler for application errors
    """

    resp = err.error_message()
    _LOG.debug('error message resp is %r', resp)
    encoder = getattr(g, 'encoder', None)
    if encoder:
        response = encoder.encode(resp)
    if isinstance(resp, dict):
        response = json.dumps(resp)
    else:
        response = resp
    resp = make_response(response, err.status_code)
    resp.headers['Content-Type'] = getattr(g, 'best_accept', None)
    return resp


# [R0912(too-many-branches), before_request] Too many branches (14/12)
@APP.before_request
def before_request():  # pylint: disable=W0612, R0912
    """
    Check mime types
    """
    headers = request.headers
    encoder = None
    _LOG.debug('accept header is %r', headers['Accept'])
    accept_header = headers['Accept']
    if accept_header in DEFAULT_MIME_TYPES:
        encoder = setup_mime(accept_header)
    else:
        mime_match = MIME_REGEX.match(accept_header)
        if mime_match:
            (_, mimetype) = mime_match.groups()
            if mimetype:
                encoder = setup_mime("application/" + mimetype)
    if encoder is None:
        if (
                '*/*' in headers['Accept'] and
                request.method.lower() in ['get', 'options']
        ):
            accept_header = 'application/yaml'
            encoder = setup_mime(accept_header)
        else:
            raise error.APIError('Oops. Unrecognizable Accept MIME',
                                 http.client.NOT_ACCEPTABLE)
    setattr(g, 'encoder', encoder)
    setattr(g, 'best_accept', accept_header)
    _LOG.debug('content type check request.data is %r', request.data)
    if request.data.decode():
        decoder = None
        if 'Content-Type' in headers:
            if headers['Content-Type'] in DEFAULT_MIME_TYPES:
                decoder = setup_mime(headers['Content-Type'])
            else:
                contentmime_match = MIME_REGEX.match(headers['Content-Type'])
                if contentmime_match:
                    (_, contentmimetype) = contentmime_match.groups()
                    if contentmimetype:
                        decoder = setup_mime("application/" + contentmimetype)
        if decoder is None:
            raise error.APIError('Oops. Unrecognizable Content-Type MIME',
                                 http.client.UNSUPPORTED_MEDIA_TYPE)
        _LOG.debug('Decoder is %r', decoder)
        setattr(g, 'decoder', decoder)
        setattr(g, 'contenttype', headers['Content-Type'])

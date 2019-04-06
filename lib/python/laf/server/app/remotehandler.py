"""Dispatching of LAF Lone's operations to remote handlers"""
import configparser
import copy
import glob
import logging
import os
import asyncio
import asyncio.subprocess
import http.client
import signal
import functools
import json
import time
import urllib.parse
import pkg_resources
import requests
import yaml
# E0401: Unable to import 'requests_kerberos'
# W0611: Unused HTTPKerberosAuth imported from requests_kerberos
import requests_kerberos  # pylint: disable=E0401
from requests_kerberos import HTTPKerberosAuth  # pylint: disable=E0401, W0611

_LOG = logging.getLogger(__name__)

HTTP_VERBS = ['get', 'create', 'delete', 'update']
_LAF_LR_REQ_PAUSE = 5


def get_notification_module(notification_type):
    """Import and return notification module.
    """
    plugin = None
    for ep in pkg_resources.iter_entry_points(
            group='notification', name=notification_type):
        plugin = ep.load()
    if plugin is None:
        raise NotImplementedError(
            'Unknown notification mechanism %r' % notification_type)
    return plugin


def get_authentication_for_request():
    """
    Get auth details for requests module
    """
    auth = None
    if 'LAF_CONFIG' in os.environ:
        family_config_dir = os.environ['LAF_CONFIG']
        defaultauth = os.path.join(family_config_dir, 'defaultauth')
        authconfig = configparser.ConfigParser(allow_no_value=True)
        authconfig.read(defaultauth)
        if 'auth_mechanism' in authconfig:
            if 'kerberos' in authconfig['auth_mechanism']:
                auth_args = authconfig['auth_args']
                principal = auth_args.get('principal')
                mutual_auth = auth_args.getint('mutual_authentication')
                auth = requests_kerberos.HTTPKerberosAuth(
                    principal=principal,
                    mutual_authentication=mutual_auth)
    return auth


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
        return (accept, lone_files[0])
    else:
        return (None, None, None)


def get_request_status(rqid, hostport, auth):
    """
    Get status from journal
    """
    url = 'http://{0}/status/{1}'.format(hostport,
                                         rqid)
    header = {'Accept': 'application/json'}
    response = requests.get(url, headers=header, auth=auth)
    if response.status_code == http.client.PROCESSING:
        return "Task in Progress"
    try:
        resp = response.json()
    except ValueError as _:
        pass
    if response.status_code == http.client.NOT_FOUND:
        resp = {"_error": "Task not found"}
    return resp


def shutdown(loop=None):
    """
    Cancel all the tasks
    """
    for task in asyncio.Task.all_tasks():
        task.cancel()
    if loop:
        loop.call_soon(loop.stop)


def queryform(explode, key, value):
    """
    Form serialization
    """
    urlpart = None
    if isinstance(value, str):
        urlpart = key + '=' + value
        return urlpart
    if isinstance(value, int):
        urlpart = key + '=' + str(value)
        return urlpart
    if not explode:
        if isinstance(value, list):
            flag = False
            for val in value:
                if flag:
                    urlpart = urlpart + ',' + val
                else:
                    urlpart = key + '=' + val
                    flag = True
            return urlpart
        if isinstance(value, dict):
            flag = False
            for valid, val in value.items():
                if flag:
                    urlpart = urlpart + ',' + valid + ',' + val
                else:
                    urlpart = key + '=' + valid + ',' + val
                    flag = True
        return urlpart
    return urlpart


def get_urlpart(querypara, key, value):
    """
    Query parameter serialization
    """
    urlpart = None
    if querypara['style'] == 'form':
        urlpart = queryform(querypara['explode'],
                            key,
                            value)
        return urlpart
    return urlpart


def updated_url(req, openapifile):
    """
    Update url for search queries
    """
    flag = False
    queryurl = None
    url_part = None
    with open(openapifile) as infile:
        spec = json.load(infile)
    parameter_spec = copy.deepcopy(spec['components']['parameters'])
    for key, value in req.obj.items():
        if key in parameter_spec:
            url_part = get_urlpart(parameter_spec[key], key, value)
        if flag:
            queryurl = queryurl + "&" + url_part
        else:
            queryurl = url_part
            flag = True
    return queryurl


def get_path_for_request(url, req, rsrcpara_types):
    """
    Create the path format
    """
    givenpath = req.path.lstrip('/')
    pathsvar = givenpath.split('/')
    flag = False
    for pathvar in pathsvar:
        if pathvar in rsrcpara_types:
            url = url + '/' + pathvar
            flag = False
        else:
            if flag is True:
                url = url + '%2f' + urllib.parse.quote(pathvar, safe='')
            else:
                url = url + '/' + urllib.parse.quote(pathvar, safe='')
                flag = True
    return url


def update_req_path(url, req, openapifile):
    """
    update req path
    """
    with open(openapifile) as infile:
        spec = json.load(infile)
    rsrcpara_types = list(spec['components']['schemas'].keys())
    return get_path_for_request(url, req, rsrcpara_types)


# R0912: Too many branches
# R0915: Too many statements
# pylint: disable=R0912, R0915


@asyncio.coroutine
def httpreq(loop, future, url, method, req, auth,
            hostport, accept, openapifile, laf_notify):
    """
    Coroutine to send http request
    """
    header = {
        'Accept': accept,
        'LAF-TX-ID': req.txid,
        'LAF-ROLE': req.role,
        'LAF-CM': req.cm,
        'LAF-OBO': req.obo
    }
    if req.obj:
        header['Content-Type'] = accept
    if method == 'get' and not req.pk:
        urlpart = updated_url(req, openapifile)
        if urlpart:
            url = url + '?' + urlpart
        while True:
            print('URL is {0}'.format(url))
            try:
                future1 = loop.run_in_executor(
                    None,
                    functools.partial(getattr(requests,
                                              method),
                                      url,
                                      headers=header,
                                      auth=auth))
                response1 = yield from future1
            except requests.exceptions.ConnectionError as err:
                future.set_result({"_error": "HTTP Error " + str(err)})
                break
            try:
                resp = response1.json()
            except ValueError as _:
                future.set_result({
                    "_error": "HTTP Error " + str(response1.status_code)})
                break
            if '_elem' in resp:
                if '_next' in resp['_links']:
                    print(yaml.dump(resp['_elem'], default_flow_style=False))
                    url = resp['_links']['_next']['href']
                    if urlpart:
                        url = url + '&' + urlpart
                else:
                    future.set_result(resp['_elem'])
                    break
            else:
                future.set_result(resp)
                break
    else:
        indata = None
        if req.obj:
            indata = json.dumps(req.obj)
        print("URL is {0}".format(url))
        try:
            future1 = loop.run_in_executor(
                None,
                functools.partial(getattr(requests,
                                          method),
                                  url,
                                  data=indata,
                                  headers=header,
                                  auth=auth))
            response1 = yield from future1
        except requests.exceptions.ConnectionError as err:
            future.set_result({"_error": "HTTP Error " + str(err)})
            shutdown()
            if not laf_notify:
                loop.call_soon(loop.stop)
            return
        if response1.status_code == http.client.ACCEPTED:
            time.sleep(_LAF_LR_REQ_PAUSE)
            url = 'http://{0}/'.format(hostport)
            url = url + response1.headers['location']
            header = {'Accept': 'application/json'}
            while True:
                try:
                    future2 = loop.run_in_executor(
                        None,
                        functools.partial(getattr(requests,
                                                  'get'),
                                          url,
                                          headers=header,
                                          auth=auth))
                    response1 = yield from future2
                except requests.exceptions.ConnectionErrori as err:
                    future.set_result({"_error": "HTTP Error " + str(err)})
                    shutdown()
                    if not laf_notify:
                        loop.call_soon(loop.stop)
                    return
                if response1.status_code != http.client.PROCESSING:
                    break
                time.sleep(_LAF_LR_REQ_PAUSE)
            if response1.status_code == http.client.OK:
                try:
                    resp = response1.json()['payload']
                except ValueError as _:
                    resp = {
                        "_error": "HTTP Error " + str(response1.status_code)}
            else:
                resp = response1.json()
            future.set_result(resp)
        elif response1.status_code == http.client.NO_CONTENT:
            future.set_result(None)
        else:
            try:
                resp = response1.json()
            except ValueError as _:
                resp = {"_error": "HTTP Error " + str(response1.status_code)}
            future.set_result(resp)
    shutdown()
    if not laf_notify:
        loop.call_soon(loop.stop)
    return


def remote_handler(lone, requestlist, configdict, options):
    """
    Remote handler for request
    """
    res = []
    for request in requestlist:
        res.append(_run_handler(lone, request, configdict, options))

    return res


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


def generate_url(urlprefix, lone, req, openapifile):
    """
    Generate the url
    """
    url = 'http://{0}/{1}'.format(urlprefix,
                                  lone.name)
    if req.pk:
        url = url + '/' + urllib.parse.quote(req.pk, safe='')
    if req.verb not in HTTP_VERBS:
        url = url + ':' + req.verb
    if req.verb in HTTP_VERBS and req.pk:
        if req.path:
            url = update_req_path(url, req, openapifile)
            req.obj = req.body
    return url


def get_url_prefix(configdict, options):
    """
    Get the url prefix based on options
    """
    if 'servers' in options:
        urlprefix = configdict['servers']['http'][0]
    else:
        urlprefix = configdict['url_prefix']
    return urlprefix


def _run_handler(lone, req, configdict, options):
    """
    Setup coroutines for http and notification
    request and start the asyncio loop
    """
    if 'http_proxy' in os.environ:
        del os.environ['http_proxy']
    if 'https_proxy' in os.environ:
        del os.environ['https_proxy']
    urlprefix = get_url_prefix(configdict, options)
    auth = get_authentication_for_request()
    if 'status' in options:
        response = get_request_status(options['status'],
                                      urlprefix,
                                      auth)
        return response
    (accept, openapifile) = get_accept_header(lone,
                                              configdict['basedir'])
    method = get_http_method(req)
    url = generate_url(urlprefix, lone, req, openapifile)
    loop = asyncio.get_event_loop()
    future = asyncio.Future()
    laf_notification = None
    if 'notification' in configdict:
        laf_notification = configdict['notification']
    if laf_notification:
        (notify_type, notify_info) = laf_notification.split('://')
        notifymod = get_notification_module(notify_type)
        asyncio.ensure_future(
            notifymod.notificationreq(
                loop,
                req.txid,
                notify_info,
            )
        )
    asyncio.ensure_future(httpreq(loop, future, url, method.lower(),
                                  req, auth, urlprefix,
                                  accept, openapifile, laf_notification))
    loop.add_signal_handler(signal.SIGINT, functools.partial(shutdown, loop))
    loop.add_signal_handler(signal.SIGTERM, functools.partial(shutdown, loop))
    try:
        loop.run_forever()
    except KeyboardInterrupt:
        _LOG.info("Caught keyboard interrupt")
    finally:
        loop.close()
    return future.result()

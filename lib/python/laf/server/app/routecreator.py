"""
Create parts of flask route based on openapi 3.0
"""
import logging
import re

_LOG = logging.getLogger(__name__)

PATH_PARAMETER = re.compile(r'\{([^}]*)\}')
PATH_PARAMETER_CONVERTERS = {
    'integer': 'int',
    'number': 'float',
    'string': 'string',
    'object': 'string',
}


def get_converted_path(match, types):
    """
    Convert openapi path to flask route
    """
    name = match.group(1)
    openapi_type = types.get(name)
    converter = PATH_PARAMETER_CONVERTERS.get(openapi_type)
    return '<{0}{1}{2}>'.format(converter or '',
                                ':' if converter else '',
                                name)


def generate_path_route(openapi_path, parameters, resolver):
    """
    Generate flask route from openapi path
    """
    parameter_dict = {}
    for parameter in parameters:
        (para_name, para_type) = get_parameter_types(parameter, resolver)
        parameter_dict[para_name] = para_type
    return PATH_PARAMETER.sub(lambda match: get_converted_path(match,
                                                               parameter_dict),
                              openapi_path)


def get_parameter_types(parameter, resolver):
    """
    Get the type of parameter
    by resolving reference
    """
    if '$ref' in parameter:
        (para_name, para_type) = resolve_reference(resolver, parameter['$ref'])
        return (para_name, para_type)
    if 'schema' in parameter:
        para_name = parameter['name']
        if 'type' in parameter['schema']:
            return (para_name, parameter['schema']['type'])
        if '$ref' in parameter['schema']:
            (_, para_type) = resolve_reference(resolver,
                                               parameter['schema']['$ref'])
            return (para_name, para_type)
    return(None, None)


def resolve_reference(resolver, ref):
    """
    Resolving recursive reference
    """
    (para_name, para_type) = (None, None)
    while True:
        _LOG.debug("resolving the reference %r", ref)
        val = resolver.resolve(ref)
        _LOG.debug("resolved reference %r", val)
        if 'type' in val[1]:
            _LOG.debug("resolve reference %r", val[1]['type'])
            para_type = val[1]['type']
            return (para_name, para_type)
        if 'schema' in val[1] and '$ref' in val[1]['schema']:
            para_name = val[1]['name']
            ref = val[1]['schema']['$ref']
        else:
            return (para_name, para_type)
    return (None, None)


def get_parameter_definition(parameter, resolver):
    """
    Get parameter definition from openapi schema
    """
    if '$ref' in parameter:
        return resolver.resolve(parameter['$ref'])
    return parameter


def generate_parameter_definition(parameters, resolver):
    """
    Generate parameter definition for all parameters
    in the given path
    """
    parameter_dict = {
        'path': dict(),
        'query': dict()
    }
    _LOG.debug("generate parameters %r", parameters)
    for parameter in parameters:
        if 'name' in parameter:
            parameter_dict[parameter['in']][parameter['name']] = parameter
        if '$ref' in parameter:
            para_ref = get_parameter_definition(parameter, resolver)
            parameter_dict[
                parameter['in']][para_ref[1]['name']] = para_ref[1]
    return parameter_dict


def get_response_definition(response, resolver):
    """
    Get response definition from openapi schema
    """
    if '$ref' in response:
        resp_ref = resolver.resolve(response['$ref'])
        return resp_ref[1]
    if 'content' in response:
        return response
    return None


def generate_response_defintion(responses, resolver):
    """
    Generate response  definition for all responses
    in the given path
    """
    response_dict = {}
    for code, response in responses.items():
        resp = get_response_definition(response, resolver)
        response_dict[code] = resp
    return response_dict


def generate_kwargs(action, resolver):
    """
    Generate view function
    """
    kwargs = dict()
    kwargs['parameters'] = generate_parameter_definition(action['parameters'],
                                                         resolver)
    _LOG.debug("parameter is %r", kwargs['parameters'])
    if 'requestBody' in action:
        kwargs['requestbody'] = action['requestBody']
    else:
        kwargs['requestbody'] = None
    _LOG.debug("request body is %r", kwargs['requestbody'])
    kwargs['responses'] = generate_response_defintion(action['responses'],
                                                      resolver)
    _LOG.debug("responses is %r", kwargs['responses'])
    return kwargs


def generate_schema_obj(content_type,
                        parameters,
                        requestbody):
    """
    Generate schema object
    for validation
    """
    required = list()
    schema_obj = {
        "type": "object",
        "properties": dict(),
        "additionalProperties": False
    }
    path_obj = {
        "type": "object",
        "properties": dict(),
        "additionalProperties": False,
        "required": list()
    }
    query_obj = {
        "type": "object",
        "properties": dict(),
        "additionalProperties": False,
        "required": list()
    }
    for path_para, path_val in parameters['path'].items():
        path_obj['properties'][path_para] = path_val['schema']
        if 'required' in path_val and path_val['required']:
            path_obj['required'].append(path_para)
    for query_para, query_val in parameters['query'].items():
        query_obj['properties'][query_para] = query_val['schema']
        if 'required' in query_val and query_val['required']:
            query_obj['required'].append(query_para)
    if path_obj['properties']:
        schema_obj['properties']['path'] = path_obj
        if path_obj['required']:
            required.append('path')
    if query_obj['properties']:
        schema_obj['properties']['query'] = query_obj
        if query_obj['required']:
            required.append('query')
    if requestbody:
        if 'content' in requestbody:
            if 'required' in requestbody and requestbody[
                    'required']:
                required.append('body')
            schema_obj['properties']['body'] = requestbody[
                'content'][content_type]['schema']
    schema_obj['required'] = required
    return schema_obj


def generate_resp_obj(content_type, responses):
    """
    Generate response object
    """
    resp_obj = {
        "type": "object",
        "properties": dict(),
        "additionalProperties": False,
    }
    for resp_key, resp_val in responses.items():
        if 'content' in responses[resp_key] and (
                'schema' in resp_val['content'][content_type]
        ):
            resp_obj['properties'][resp_key] = resp_val[
                'content'][content_type]['schema']
        else:
            resp_obj['properties'][resp_key] = resp_val
    return resp_obj

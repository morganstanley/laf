"""
wsgi plugin load
"""
import pkg_resources


def get_authentication_plugin(mechanism):
    """Import and return the wsgi plugin.
    """
    plugin = None
    for ep in pkg_resources.iter_entry_points(
            group='authentication_mechanism', name=mechanism):
        plugin = ep.load()
    if plugin is None:
        raise NotImplementedError('Unknown wsgi plugin %r' % mechanism)
    return plugin

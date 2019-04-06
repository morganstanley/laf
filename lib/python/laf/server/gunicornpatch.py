"""
Patch to remove quoting in gunicorn
"""

import logging
from gunicorn.http import wsgi
# W0611: unused-import
from gunicorn import _compat  # pylint: disable=W0611

_LOG = logging.getLogger(__name__)

_ORIG_UNQUOTE_STR = wsgi.unquote_to_wsgi_str


def _unquote_to_wsgi_str(string):
    """
    Do not unquote path_info
    """
    return string.encode('utf-8').decode('latin-1')


wsgi.unquote_to_wsgi_str = _unquote_to_wsgi_str

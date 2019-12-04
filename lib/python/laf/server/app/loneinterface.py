"""
Interface module
for laf lones
"""
import importlib
import inspect
import logging
import pydoc


__all__ = ["LoneAPI", "longrunning", "journallog"]

_LOG = logging.getLogger(__name__)


def longrunning(handler):
    """
    Function attribute to declare
    long running handler
    """
    handler.is_long_running = True
    return handler


def journallog(handler):
    """
    Function attribute to declare
    handler needs to be journaled
    """
    handler.is_journaled = True
    return handler


class LoneAPI():
    """
    Lone API class
    """
    def __init__(self, cfg=None):
        """
        """
        self._name = self.__class__.format_name()
        self._request = None
        self._cfg = cfg
        if self.mode == 'server':
            self.services = importlib.import_module(
                'laf.server.app.services'
            )

    def enter_request(self, request):
        """
        Takes care of the request context
        """
        self._request = request
        return self

    def __enter__(self):
        assert self._request is not None
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self._request = None

    @property
    def name(self):
        """
        The Lone's name property.
        """
        return self._name

    @property
    def basedir(self):
        """
        Base directory of laf lone
        """
        if 'basedir' in self._cfg:
            return self._cfg['basedir']
        return None

    @property
    def deployment(self):
        """
        Deployment of laf lone
        """
        if 'deployment' in self._cfg:
            return self._cfg['deployment']
        return None

    @property
    def family(self):
        """
        Family of laf lone
        """
        if 'family' in self._cfg:
            return self._cfg['family']
        return None

    @property
    def user(self):
        """
        User submitting the request
        """
        return self._request.effective_user

    @property
    def host(self):
        """
        Host from which request
        was sent
        """
        return self._request.host

    @property
    def txid(self):
        """
        Return request transaction id
        """
        return self._request.txid

    @property
    def obo(self):
        """
        Return request obo
        """
        return self._request.obo

    @property
    def role(self):
        """
        Return request role
        """
        return self._request.role

    @property
    def cm(self):
        """
        Return change management
        ticket
        """
        return self._request.cm

    @property
    def mode(self):
        """
        Return mode of laf
        """
        if 'mode' in self._cfg:
            return self._cfg['mode']
        else:
            return 'lone'

    @classmethod
    def format_name(cls):
        """
        The Lone's name.
        """
        return cls.__name__.lower()

    @classmethod
    def help(cls):
        """
        The Lone's help.
        """
        return pydoc.render_doc(cls, title='Lone Documentation: %s')

    def laf_status(self, msg):
        """
        Send laf status to notification process or stdout
        """
        if self.mode == 'server':
            if 'notification' in self._cfg:
                self.services.publish(self.txid, msg)
        else:
            print('[log] {0}'.format(msg.split('/n')))

    def laf_error(self, msg):
        """
        logging level is error
        """
        _LOG.error('[%s]: %s', self.txid, msg)

    def laf_info(self, msg):
        """
        logging level is info
        """
        _LOG.info('[%s]: %s', self.txid, msg)

    def laf_debug(self, msg):
        """
        logging level is debug
        """
        _LOG.debug('[%s]: %s', self.txid, msg)


def load_lone_from_module(lone, laf_config):
    """
    Load laf module
    """
    spec = importlib.util.find_spec(lone)
    lonemodule = spec.loader.load_module()
    for _, inst in inspect.getmembers(lonemodule, inspect.isclass):
        if issubclass(inst, LoneAPI):
            # Found a lone class, invoke it
            return inst(laf_config)
    return None

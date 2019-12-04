"""LAF request"""

import socket
import getpass
import uuid
import yaml

__all__ = ['Request', 'get_laf_rq_id']


class Request():
    """
    LAF Request class
    """
    __slots__ = ['lone', 'verb', 'pk', 'obj', 'role', 'mode',
                 'txid', 'rqid', 'user', 'effective_user',
                 'host', 'obo', 'cm', 'subhandler', '_yaml',
                 'body', 'path', 'urlvars', 'queryvars']
    # W0613: Unused argument 'rqid', how to use rqid??

    def __init__(self,
                 user=None,
                 obo=None,
                 role=None,
                 host=None,
                 lone=None,
                 pk=None,
                 verb=None,
                 txid=None,
                 rqid=None,  # pylint: disable=W0613
                 cm=None,
                 obj=None,
                 subhandler=None,
                 _yaml=None,
                 body=None,
                 path=None,
                 urlvars=None,
                 queryvars=None,
                 mode='server'):
        self.user = user
        self.obo = obo
        self.role = role
        self.host = host
        self.lone = lone
        self.pk = pk
        self.verb = verb
        self.txid = txid
        self.cm = cm
        self.obj = obj
        self.body = body
        self.path = path
        self.urlvars = urlvars
        self.queryvars = queryvars
        self.subhandler = subhandler
        self._yaml = _yaml
        self.mode = mode
        self.rqid = get_laf_rq_id()
        if txid is None:
            self.txid = self.rqid
        if user is None:
            self.user = getpass.getuser()
        if host is None:
            self.host = socket.gethostname()
        if obo:
            self.effective_user = obo
        else:
            self.effective_user = self.user

    @property
    def yaml(self):
        """
        Convert the object to yaml
        """
        if self._yaml is None:
            self._yaml = yaml.dump(self.obj)
        return self._yaml


def get_laf_rq_id():
    """
    Generate a LAF_RQ_ID.

    @rtype: string
    @return: The Lone's transaction ID string.
    """
    rqid = str(uuid.uuid4())
    return rqid

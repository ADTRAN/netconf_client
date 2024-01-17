from lxml import etree
from netconf_client.constants import NAMESPACES


class NetconfClientException(Exception):
    """Base class for all ``netconf_client`` exceptions"""

    pass


class SessionClosedException(NetconfClientException):
    """This exception is raised on any futures when the NETCONF connection is closed"""

    pass


class RpcError(NetconfClientException):
    """This exception is raised on a future from an ``<rpc>`` call that
    returns a corresponding ``<rpc-error>``

    :ivar reply_raw: The raw text that was returned by the server
    :ivar reply_ele: The lxml parsed representation of the reply
    :ivar message: If present, the contents of the ``<error-message>`` tag
    :ivar tag: If present, the contents of the ``<error-tag>`` tag
    :ivar info: If present, the contents of the ``<error-info>`` tag

    """

    def __init__(self, raw, ele):
        self.reply_raw = raw
        self.reply_ele = ele

        msgs = ele.xpath(
            "/nc:rpc-reply/nc:rpc-error/nc:error-message", namespaces=NAMESPACES
        )
        if msgs:
            msg = msgs[0].text
            self.message = msg
        else:
            msg = "RPC Error"

        tags = ele.xpath(
            "/nc:rpc-reply/nc:rpc-error/nc:error-tag", namespaces=NAMESPACES
        )
        if tags:
            self.tag = tags[0].text

        # For ncclient compatibility
        self.severity = "error"

        err_info = ele.xpath(
            "/nc:rpc-reply/nc:rpc-error/nc:error-info", namespaces=NAMESPACES
        )
        if err_info:
            self.info = etree.tostring(err_info[0])

        super(RpcError, self).__init__(msg)


class NetconfProtocolError(NetconfClientException):
    """This exception is raised on any NETCONF protocol error"""

    pass


class InvalidSSHHostkey(NetconfClientException):
    """This exception is raised if the SSH hostkey isn't valid"""

    pass

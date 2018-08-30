from lxml import etree

from netconf_client.error import RpcError

from common import RPC_ERROR_WITH_MSG, RPC_ERROR_WITHOUT_MSG


def test_rpc_error_msg():
    e = RpcError(RPC_ERROR_WITH_MSG, etree.fromstring(RPC_ERROR_WITH_MSG))
    assert e.reply_raw == RPC_ERROR_WITH_MSG
    assert str(e) == "MTU value 25000 is not within range 256..9192"


def test_rpc_error_no_msg():
    e = RpcError(RPC_ERROR_WITHOUT_MSG, etree.fromstring(RPC_ERROR_WITHOUT_MSG))
    assert e.reply_raw == RPC_ERROR_WITHOUT_MSG
    assert str(e) != ""

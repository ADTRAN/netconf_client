from threading import Thread
from concurrent.futures import Future
from queue import Queue, Empty

from lxml import etree

from netconf_client.parser import parse_messages
from netconf_client.log import logger
from netconf_client.constants import DEFAULT_HELLO, NAMESPACES, CAP_NETCONF_11
from netconf_client.error import SessionClosedException, RpcError


class Session:
    """A session with a NETCONF server

    This class is a context manager, and should always be either used
    with a ``with`` statement or the :meth:`close` method should be
    called manually when the object is no longer required.

    :ivar server_capabilities: The list of capabilities parsed from
                               the server's ``<hello>``

    :ivar client_capabilities: The list of capabilities parsed from
                               the client's ``<hello>``

    """

    def __init__(self, sock):
        self.sock = sock
        self.mode = "1.0"

        self.send_msg(DEFAULT_HELLO)
        self.client_hello = DEFAULT_HELLO

        self.parser = parse_messages(sock, self.mode)

        # First message will be the server hello
        self.server_hello = next(self.parser)
        server_ele = etree.fromstring(self.server_hello)
        self.session_id = int(
            server_ele.xpath("/nc:hello/nc:session-id", namespaces=NAMESPACES)[0].text
        )
        self.server_capabilities = capabilities_from_hello(server_ele)

        client_ele = etree.fromstring(self.client_hello)
        self.client_capabilities = capabilities_from_hello(client_ele)

        if (
            CAP_NETCONF_11 in self.client_capabilities
            and CAP_NETCONF_11 in self.server_capabilities
        ):
            self.mode = "1.1"

        self.unknown_recvq = Queue()
        self.notifications = Queue()
        self.rpc_reply_futures = Queue()
        self.thread = Thread(target=self._recv_loop)
        self.thread.daemon = True
        self.thread.start()

    def __enter__(self):
        return self

    def __exit__(self, _, __, ___):
        self.close()

    def close(self):
        """Closes any associated sockets and frees any other associated resources"""
        try:
            self.sock.close()
        except Exception:
            pass

        try:
            while True:
                f = self.rpc_reply_futures.get(block=False)
                f.set_exception(SessionClosedException())
                self.rpc_reply_futures.task_done()
        except Empty:
            pass

    def send_msg(self, msg):
        """Sends a raw byte string to the server

        :param bytes msg: The byte string to send
        """
        logger.debug("Sending message on session %s", msg)
        if self.mode == "1.0":
            self.sock.sendall(msg + b"]]>]]>")
        elif self.mode == "1.1":
            self.sock.sendall(frame_message_11(msg))

    def send_rpc(self, rpc):
        """Sends a raw RPC to the server

        :param bytes rpc: The RPC to send

        :rtype: :class:`concurrent.futures.Future` with a result type
                of tuple(:class:`bytes`, :class:`lxml.Element`)

        """
        f = Future()
        self.rpc_reply_futures.put(f)
        self.send_msg(rpc)
        return f

    def _recv_loop(self):
        while True:
            try:
                msg = self.parser.send(self.mode)
                ele = etree.fromstring(msg)
            except Exception as e:
                logger.info("Stopping recv thread due to exception %s", str(e))
                return

            if ele.xpath("/nc:rpc-reply", namespaces=NAMESPACES):
                try:
                    f = self.rpc_reply_futures.get(block=False)

                    if ele.xpath("/nc:rpc-reply/nc:rpc-error", namespaces=NAMESPACES):
                        f.set_exception(RpcError(msg, ele))
                    else:
                        f.set_result((msg, ele))
                    self.rpc_reply_futures.task_done()
                    msg = None
                except Empty:
                    logger.warning(
                        "An <rpc-reply> was received "
                        "with no corresponding handler: %s",
                        msg,
                    )
            elif ele.xpath("/notif:notification", namespaces=NAMESPACES):
                self.notifications.put((msg, ele))
                msg = None

            if msg is not None:
                self.unknown_recvq.put((msg, ele))


def capabilities_from_hello(hello):
    return [
        x.text
        for x in hello.xpath(
            "/nc:hello/nc:capabilities/nc:capability", namespaces=NAMESPACES
        )
    ]


def frame_message_11(msg):
    header = "\n#{}\n".format(len(msg)).encode("ascii")
    footer = b"\n##\n"
    return header + msg + footer

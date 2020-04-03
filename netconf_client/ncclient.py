from datetime import datetime
import logging
import inspect
from concurrent.futures import CancelledError, TimeoutError
from six.moves.queue import Empty
from lxml import etree

from netconf_client.error import RpcError
from netconf_client.rpc import (
    edit_config,
    get,
    get_config,
    copy_config,
    discard_changes,
    commit,
    lock,
    unlock,
    kill_session,
    close_session,
    create_subscription,
    validate,
    make_rpc,
    delete_config,
)


# Defines the scope for netconf traces
logger = logging.getLogger("netconf_client_pretty")


def pretty_xml(xml):
    """Reformats a given string containing an XML document (for human readable output)"""

    parser = etree.XMLParser(remove_blank_text=True)
    tree = etree.fromstring(xml, parser)
    return etree.tostring(tree, pretty_print=True).decode()


class Manager:
    """A helper class for performing common NETCONF operations with pretty logging.

    This class attempts to be API compatible with the manager object
    from the original ncclient.

    This class is also a context manager and can be used with `with`
    statements to automatically close the underlying session.

    NetConf requests and responses are logged using the 'netconf_client' scope.
    The API functions, which are to be logged, can be configured (default: all but 'close_session').
    Also the log level can be changed via API (logger.DEBUG is the default).

    Each log entry shows a log ID (the peer's IP address as default).
    Also a timestamp is printed for each request/response message and the round-trip delay
    between request and its response is computed and displayed.

    :ivar float timeout: Duration in seconds to wait for a reply

    :ivar session: The underlying
                   :class:`netconf_client.session.Session` connected
                   to the server
    :ivar str log_id: application-specific log ID (None as default)
    :ivar int log_level: logging level (logging.DEBUG as default)

    """

    def __init__(self, session, timeout=120, log_id=None):
        """Construct a new Manager object

        :param session: The low-level NETCONF session to use for requests
        :type session: :class:`netconf_client.session.Session`

        :param float timeout: Duration in seconds to wait for replies
        :param string log_id: log ID string printed with each log entry,
               the peer's IP address as default
        """
        self.timeout = timeout
        self.session = session
        self.log_id = log_id
        self.start_time = self._get_timestamp()
        self.log_level = logging.DEBUG

        self.logged_functions = {
            "get": True,
            "edit_config": True,
            "get_config": True,
            "copy_config": True,
            "discard_changes": True,
            "commit": True,
            "lock": True,
            "unlock": True,
            "kill_session": True,
            "create_subscription": True,
            "validate": True,
            "delete_config": True,
            "dispatch": True,
            "close_session": False,
        }

    def __enter__(self):
        return self

    def __exit__(self, a, b, c):
        self.session.__exit__(a, b, c)

    @staticmethod
    def get_logger():
        """Returns the internally used logger instance (same for all sessions)"""
        return logger

    def get_log_level(self):
        """Returns current logging level, default is DEBUG"""
        return self.log_level

    def set_log_level(self, level=logging.DEBUG):
        """Sets the log level to use for logging"""
        self.log_level = level

    def get_peer_ip(self):
        """Returns the peer's IP address.
           If not connected, an empty string is returned.
        """

        addr = ""
        try:
            s = self.session.sock.sock
            (addr, _) = s.getpeername()
        except:
            pass
        return addr

    def get_request_log_id(self):
        """Returns string containing device type, device num (if any),
           and IP address
        """
        peer_ip = self.get_peer_ip()
        if self.log_id:
            if peer_ip:
                return " => {} ({})".format(self.log_id, peer_ip)
            return " => {}".format(self.log_id)
        if peer_ip:
            return " => {}".format(peer_ip)
        return ""

    def get_response_log_id(self):
        """Returns string containing device type and device num (if any),
           IP address otherwise
        """
        if self.log_id:
            return " <= {}".format(self.log_id)
        peer_ip = self.get_peer_ip()
        if peer_ip:
            return " <= {}".format(peer_ip)
        return ""

    def get_logged_functions(self):
        """Returns a dict 'str'->'Boolean' of function names to be logged"""
        return self.logged_functions

    def is_function_logged(self, funcname):
        """Checks whether a given function is enabled for logging"""
        return self.logged_functions.get(funcname, False)

    def enable_logging(self, funcname):
        """Enables logging for given function name"""
        if funcname in self.logged_functions:
            self.logged_functions.update({funcname: True})

    def disable_logging(self, funcname):
        """Disables logging for given function name"""
        if funcname in self.logged_functions:
            self.logged_functions.update({funcname: False})

    def _get_timestamp(self):
        return datetime.now()

    def _is_logger_enabled(self, funcname):
        return self.is_function_logged(funcname) and Manager.get_logger().isEnabledFor(
            self.get_log_level()
        )

    def _log_rpc_request(self, rpc_xml, funcname):
        if self._is_logger_enabled(funcname):
            conn_id = self.get_request_log_id()
            self.start_time = self._get_timestamp()
            pretty = pretty_xml(rpc_xml)

            Manager.get_logger().log(
                self.get_log_level(),
                "%s: NC Request%s:\n%s",
                self.start_time,
                conn_id,
                pretty,
            )

    def _log_rpc_response(self, rpc_xml, funcname):
        if self._is_logger_enabled(funcname):
            end_time = self._get_timestamp()
            conn_id = self.get_response_log_id()

            taken = end_time - self.start_time
            taken_formatted = "%d.%03d" % (taken.seconds, taken.microseconds / 1000)
            pretty = pretty_xml(rpc_xml) if rpc_xml else "(None)"

            Manager.get_logger().log(
                self.get_log_level(),
                "%s: NC Response%s (%s sec):\n%s",
                end_time,
                conn_id,
                taken_formatted,
                pretty,
            )

    def _log_rpc_failure(self, message, funcname):
        if self._is_logger_enabled(funcname):
            end_time = self._get_timestamp()
            conn_id = self.get_response_log_id()

            taken = end_time - self.start_time
            # we accept a small rounding error of 0.5 ms
            taken_formatted = "%d.%03d" % (taken.seconds, taken.microseconds / 1000)
            if message:
                message = "Cause: {}\n".format(message)

            Manager.get_logger().log(
                self.get_log_level(),
                "%s: NC Failure %s (%s sec)\n%s",
                end_time,
                conn_id,
                taken_formatted,
                message,
            )

    def send_rpc(self, rpc_xml):
        """Send given NC request message and expect an NC response

           Both, the NC request and response messages are logged with timestamp.
           In case of failure or exceptions, the error cause is logged, if known.
           Exceptions thrown by functions called by send_rpc() are re-raised
           after they have been logged.

           :param str rpc_xml: XML RPC message to sent to NC server

           :rtype :tupel: (`str` raw XML response, `ElementTree`: Element Tree or None)
           :exception: whatever exceptions raised by /netconf-client/netconf_client/ncclient.py
        """

        (raw, ele) = (None, None)
        funcname = inspect.stack()[1][3]
        self._log_rpc_request(rpc_xml, funcname)

        try:
            f = self.session.send_rpc(rpc_xml)
            r = f.result(timeout=self.timeout)
            if not r:
                self._log_rpc_failure("RPC returned without result", funcname)
                return (raw, ele)
            (raw, ele) = f.result(timeout=self.timeout)
            self._log_rpc_response(raw, funcname)
        except CancelledError:
            self._log_rpc_failure("RPC cancelled", funcname)
            raise
        except TimeoutError:
            self._log_rpc_failure(
                "RPC timeout (max. {} seconds)".format(self.timeout), funcname
            )
            raise
        except Exception as e:
            message = str(e)
            if not message:
                message = type(e)
            self._log_rpc_failure("RPC exception: {}".format(message), funcname)
            raise
        except:
            self._log_rpc_failure("RPC exception", funcname)
            raise

        return (raw, ele)

    def edit_config(
        self,
        config,
        target="running",
        default_operation=None,
        test_option=None,
        error_option=None,
        format="xml",
    ):
        """Send an ``<edit-config>`` request

        :param str config: The ``<config>`` node to use in the request

        :param str target: The datastore to edit

        :param str default_operation: The default-operation to
                                      perform; can be ``None``,
                                      'merge', 'replace', or 'none'.

        :param str test_option: The test-option to use; can be
                               ``None``, 'test-then-set', 'set', or
                               'test-only'

        :param str error_option: The error-option to use; can be
                                 ``None``, 'stop-on-error',
                                 'continue-on-error', or
                                 'rollback-on-error'

        """
        rpc_xml = edit_config(
            config, target, default_operation, test_option, error_option
        )
        self.send_rpc(rpc_xml)

    def get(self, filter=None, with_defaults=None):
        """Send a ``<get>`` request

        :param str filter: The ``<filter>`` node to use in the request


        :param str with_defaults: Specify the mode of default
                                  reporting.  See :rfc:`6243`. Can be
                                  ``None`` (i.e., omit the
                                  with-defaults tag in the request),
                                  'report-all', 'report-all-tagged',
                                  'trim', or 'explicit'.

        :rtype: :class:`DataReply`
        """
        rpc_xml = get(filter=convert_filter(filter), with_defaults=with_defaults)
        (raw, ele) = self.send_rpc(rpc_xml)
        return DataReply(raw, ele)

    def get_config(self, source="running", filter=None, with_defaults=None):
        """Send a ``<get-config>`` request

        :param str source: The datastore to retrieve the configuration from

        :param str filter: The ``<filter>`` node to use in the request

        :param str with_defaults: Specify the mode of default
                                  reporting.  See :rfc:`6243`. Can be
                                  ``None`` (i.e., omit the
                                  with-defaults tag in the request),
                                  'report-all', 'report-all-tagged',
                                  'trim', or 'explicit'.

        :rtype: :class:`DataReply`

        """
        rpc_xml = get_config(
            source=source, filter=convert_filter(filter), with_defaults=with_defaults,
        )
        (raw, ele) = self.send_rpc(rpc_xml)
        return DataReply(raw, ele)

    def copy_config(self, target, source, with_defaults=None):
        """Send a ``<copy-config>`` request

        :param str source: The source datastore

        :param str target: The destination datastore

        :param str with_defaults: Specify the mode of default
                                  reporting.  See :rfc:`6243`. Can be
                                  ``None`` (i.e., omit the
                                  with-defaults tag in the request),
                                  'report-all', 'report-all-tagged',
                                  'trim', or 'explicit'.
        """
        rpc_xml = copy_config(target=target, source=source, with_defaults=with_defaults)
        self.send_rpc(rpc_xml)

    def discard_changes(self):
        """Send a ``<discard-changes>`` request"""
        self.send_rpc(discard_changes())

    def commit(
        self, confirmed=False, confirm_timeout=None, persist=None, persist_id=None
    ):
        """Send a ``<commit>`` request

        :param bool confirmed: Set to ``True`` if this is a confirmed-commit

        :param int confirm_timeout: When `confirmed` is ``True``, the
                                    number of seconds until the commit
                                    will be automatically rolled back
                                    if no confirmation or extension is
                                    received

        :param str persist: When `confirmed` is ``True``, sets the
                            persist-id token for the commit and makes
                            the commit a persistent commit

        :param str persist_id: When `confirmed` is ``True`` and a
                               previous ``<persist>`` was given for
                               the current commit, this field must
                               match the corresponding persist-id for
                               the commit

        """
        rpc_xml = commit(
            confirmed=confirmed,
            confirm_timeout=confirm_timeout,
            persist=persist,
            persist_id=persist_id,
        )
        self.send_rpc(rpc_xml)

    def lock(self, target):
        """Send a ``<lock>`` request

        :param str target: The datastore to be locked
        """
        self.send_rpc(lock(target))

    def unlock(self, target):
        """Send an ``<unlock>`` request

        :param str target: The datastore to be unlocked
        """
        self.send_rpc(unlock(target))

    def kill_session(self, session_id):
        """Send a ``<kill-session>`` request

        :param int session_id: The session to be killed
        """
        self.send_rpc(kill_session(session_id))

    def close_session(self):
        """Send a ``<close-session>`` request"""
        self.send_rpc(close_session())

    def create_subscription(
        self, stream=None, filter=None, start_time=None, stop_time=None
    ):
        """Send a ``<create-subscription>`` request

        Received ``<notification>`` elements can be retrieved with
        :meth:`take_notification`

        :param str stream: The event stream to subscribe to
        :param str filter: The filter for notifications to select
        :param str start_time: When replaying notifications, the earliest notifications to replay
        :param str stop_time: When replaying notifications, the latest notifications to replay

        """
        rpc_xml = create_subscription(
            stream=stream, filter=filter, start_time=start_time, stop_time=stop_time
        )
        self.send_rpc(rpc_xml)

    def validate(self, source):
        """Send a ``<validate>`` request

        :param str source: The datastore to validate
        """
        self.send_rpc(validate(source))

    @property
    def session_id(self):
        """The session ID given in the ``<hello>`` from the server"""
        return self.session.session_id

    def take_notification(self, block=True, timeout=None):
        """Retrieve a notification from the incoming notification queue.

        :param bool block: If ``True``, the call will block the
                           current thread until a notification is
                           received or until `timeout` is exceeded

        :param float timeout: The number of seconds to wait when
                              `block` is ``True``; when ``None``, the
                              call can block indefinitely

        :rtype: :class:`Notification`
        """
        try:
            (msg, ele) = self.session.notifications.get(block=block, timeout=timeout)
            return Notification(msg, ele)
        except Empty:
            return None

    def dispatch(self, rpc):
        """Send an ``<rpc>`` request

        :param str rpc: The RPC to send; it should not include an
                        ``<rpc>`` tag (one will be generated for you)

        :rtype: :class:`RPCReply`
        """
        (msg, _) = self.send_rpc(make_rpc(from_ele(rpc)))
        return RPCReply(msg)

    def delete_config(self, target):
        """Send a ``<delete-config>`` request

        :param str target: The datastore to delete
        """
        self.send_rpc(delete_config(target))


class DataReply:
    """A response containing a ``<data>`` element

    :ivar str data_xml: The data element in string form (note that
                        this value was handled by lxml)

    :ivar data_ele: The lxml parsed representation of the data

    :ivar bytes raw_reply: The raw reply from the server

    """

    def __init__(self, raw, ele):
        self.data_ele = ele.find("{urn:ietf:params:xml:ns:netconf:base:1.0}data")
        self.data_xml = etree.tostring(self.data_ele)
        self.raw_reply = raw


class RPCReply:
    """A non-error response to an ``<rpc>``

    :ivar str xml: The raw reply from the server
    """

    def __init__(self, xml):
        self.xml = xml


class Notification:
    """A ``<notification>`` received from the server

    :ivar bytes notification_xml: The raw notification as received from the server
    :ivar notification_ele: The lxml parsed representation of the notification
    """

    def __init__(self, raw, ele):
        self.notification_ele = ele
        self.notification_xml = raw


def convert_filter(filter):
    if filter is None:
        return None

    if isinstance(filter, tuple):
        (kind, value) = filter
        if kind == "subtree":
            return "<filter>{}</filter>".format(value)
        else:
            raise NotImplementedError("Unimplemented filter type {}".format(kind))

    return filter


def from_ele(maybe_ele):
    if etree.iselement(maybe_ele):
        return etree.tostring(maybe_ele).decode("utf-8")
    else:
        return maybe_ele


def to_ele(maybe_ele):
    """Convert the given string to an lxml element

    :param maybe_ele: If this is a string, it will be parsed by
                      lxml. If it is already an lxml element the
                      parameter is returned unchanged
    """
    if etree.iselement(maybe_ele):
        return maybe_ele
    else:
        return etree.fromstring(maybe_ele)


RPCError = RpcError

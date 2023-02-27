from datetime import datetime
from socket import error as socket_error
import logging
import inspect
from concurrent.futures import CancelledError, TimeoutError
from queue import Empty
from typing import Optional
import time

from lxml import etree

from netconf_client.error import RpcError
from netconf_client.rpc import (
    edit_config,
    get,
    get_config,
    copy_config,
    discard_changes,
    commit,
    cancel_commit,
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
_logger = logging.getLogger("netconf_client.manager")


def _pretty_xml(xml):
    """Reformats a given string containing an XML document (for human readable output)"""

    pretty = ""
    try:
        parser = etree.XMLParser(remove_blank_text=True)
        tree = etree.fromstring(xml, parser)
        pretty = etree.tostring(tree, pretty_print=True).decode()
    except etree.Error as e:
        pretty = "Error: Cannot format XML message: {}\nPlain message is:\n{}".format(
            str(e), xml.decode()
        )

    return pretty


class Manager:
    """A helper class for performing common NETCONF operations with pretty logging.

    This class attempts to be API compatible with the manager object
    from the original ncclient.

    This class is also a context manager and can be used with `with`
    statements to automatically close the underlying session.

    NETCONF requests and responses are logged using the ``netconf_client.manager`` scope.
    The log level is logger.DEBUG.

    Each log entry shows a log ID (the peers' IP addresses as default).
    Additionally, the round-trip delay between request and its response is
    computed and displayed.

    The Python logger receives a dictionary via `extra` parameter, whose
    key is ``ncclient.Manager.funcname`` and which contains the name of
    the API function being logged.
    This information can be used for user-specific filtering.

    :ivar float timeout: Duration in seconds to wait for a reply

    :ivar session: The underlying
                   :class:`netconf_client.session.Session` connected
                   to the server
    :ivar str log_id: application-specific log ID (None as default)

    """

    def __init__(self, session, timeout=120, log_id=None):
        """Construct a new Manager object

        :param session: The low-level NETCONF session to use for requests
        :type session: :class:`netconf_client.session.Session`

        :param float timeout: Duration in seconds to wait for replies
        :param string log_id: log ID string additionally printed with
               each log entry
        """
        self.timeout = timeout
        self.session = session
        self.log_id = log_id
        self._start_time = self._get_timestamp()
        self._local_ip = None
        self._peer_ip = None
        self._funcname = None

    def __enter__(self):
        return self

    def __exit__(self, a, b, c):
        self.session.__exit__(a, b, c)

    @staticmethod
    def logger():
        """Returns the internally used logger instance (same for all sessions)"""
        return _logger

    def set_logger_level(self, level):
        _logger.setLevel(level)

    def _get_timestamp(self):
        return datetime.now()

    def _is_logger_enabled(self):
        return Manager.logger().isEnabledFor(logging.DEBUG)

    def _fetch_connection_ip(self):
        """Retrieves and stores the connection's local and remote IP"""

        self._local_ip = None
        self._peer_ip = None
        try:
            (self._local_ip, _) = self.session.sock.sock.getsockname()
            (self._peer_ip, _) = self.session.sock.sock.getpeername()
        except (AttributeError, socket_error):
            pass

    def _get_connection_info(self, direction):
        """Returns detailed connection info for logging"""

        result = ""
        if self.log_id:
            if self._local_ip and self._peer_ip:
                result = " ({}) {} {} ({})".format(
                    self._local_ip, direction, self.log_id, self._peer_ip
                )
            else:
                result = " {} {}".format(direction, self.log_id)
        else:
            if self._local_ip and self._peer_ip:
                result = " {} {} {}".format(self._local_ip, direction, self._peer_ip)
        return result

    def _fetch_funcname(self):
        """Retrieves and stores the name of the API function being called"""
        self._funcname = inspect.stack()[3][3]

    def _log_rpc_request(self, rpc_xml):
        if self._is_logger_enabled():
            self._fetch_funcname()
            self._fetch_connection_ip()
            conn_id = self._get_connection_info("=>")
            self._start_time = self._get_timestamp()
            pretty = _pretty_xml(rpc_xml)

            Manager.logger().debug(
                "NC Request%s:\n%s",
                conn_id,
                pretty,
                extra={"ncclient.Manager.funcname": self._funcname},
            )

    def _log_rpc_response(self, rpc_xml):
        if self._is_logger_enabled():
            end_time = self._get_timestamp()
            conn_id = self._get_connection_info("<=")

            taken = end_time - self._start_time
            taken_formatted = "%d.%03d" % (taken.seconds, taken.microseconds / 1000)
            pretty = _pretty_xml(rpc_xml) if rpc_xml else "(None)"

            Manager.logger().debug(
                "NC Response%s (%s sec):\n%s",
                conn_id,
                taken_formatted,
                pretty,
                extra={"ncclient.Manager.funcname": self._funcname},
            )

    def _log_rpc_failure(self, message):
        if self._is_logger_enabled():
            end_time = self._get_timestamp()
            conn_id = self._get_connection_info("<=")

            taken = end_time - self._start_time
            taken_formatted = "%d.%03d" % (taken.seconds, taken.microseconds / 1000)
            message = "Cause: {}\n".format(message)

            Manager.logger().debug(
                "NC Failure%s (%s sec)\n%s",
                conn_id,
                taken_formatted,
                message,
                extra={"ncclient.Manager.funcname": self._funcname},
            )

    def _send_rpc(self, rpc_xml):
        """Send given NC request message and expect a NC response

        Both, the NC request and response messages are logged with timestamp.
        In case of failure or exceptions, the error cause is logged, if known.
        Exceptions thrown by functions called by _send_rpc() are re-raised
        after they have been logged.

        :param str rpc_xml: XML RPC message to sent to NC server

        :rtype :tupel: (`str` raw XML response, `ElementTree`: Element Tree or None)
        :exception: whatever exceptions raised by /netconf-client/netconf_client/ncclient.py
        """

        (raw, ele) = (None, None)
        self._log_rpc_request(rpc_xml)

        current_timestamp = time.monotonic()
        end_timestamp = current_timestamp + self.timeout
        try:
            f = self.session.send_rpc(rpc_xml)
            while current_timestamp < end_timestamp:
                timeout = end_timestamp - current_timestamp
                try:
                    r = f.result(timeout=timeout)
                    if not r:
                        self._log_rpc_failure("RPC returned without result")
                    else:
                        (raw, ele) = r
                        self._log_rpc_response(raw)
                    return (raw, ele)
                except TimeoutError:
                    current_timestamp = time.monotonic()
                    if current_timestamp >= end_timestamp:
                        raise
        except CancelledError:
            self._log_rpc_failure("RPC cancelled")
            raise
        except TimeoutError:
            self._log_rpc_failure("RPC timeout (max. {} seconds)".format(self.timeout))
            raise
        except Exception as e:
            message = str(e)
            self._log_rpc_failure("RPC exception: {}".format(message))
            raise

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
        self._send_rpc(rpc_xml)

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
        (raw, ele) = self._send_rpc(rpc_xml)
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
            source=source,
            filter=convert_filter(filter),
            with_defaults=with_defaults,
        )
        (raw, ele) = self._send_rpc(rpc_xml)
        return DataReply(raw, ele)

    def copy_config(self, target, source, with_defaults=None):
        """Send a ``<copy-config>`` request

        :param str source: The source datastore or the <config> element
                           containing the complete configuration to copy.

        :param str target: The destination datastore

        :param str with_defaults: Specify the mode of default
                                  reporting.  See :rfc:`6243`. Can be
                                  ``None`` (i.e., omit the
                                  with-defaults tag in the request),
                                  'report-all', 'report-all-tagged',
                                  'trim', or 'explicit'.
        """
        rpc_xml = copy_config(target=target, source=source, with_defaults=with_defaults)
        self._send_rpc(rpc_xml)

    def discard_changes(self):
        """Send a ``<discard-changes>`` request"""
        self._send_rpc(discard_changes())

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
        self._send_rpc(rpc_xml)

    def cancel_commit(self, persist_id: Optional[str] = None):
        """Send a ``<cancel-commit>`` request

        :param str persist_id: A persistent confirmed commit id given in the ``<commit>``
                               request. Can be None (default), if ``<cancel-commit>`` is issued
                               on the same session that issued the confirmed commit.
        """
        self._send_rpc(cancel_commit(persist_id))

    def lock(self, target):
        """Send a ``<lock>`` request

        :param str target: The datastore to be locked
        """
        self._send_rpc(lock(target))

    def unlock(self, target):
        """Send an ``<unlock>`` request

        :param str target: The datastore to be unlocked
        """
        self._send_rpc(unlock(target))

    def kill_session(self, session_id):
        """Send a ``<kill-session>`` request

        :param int session_id: The session to be killed
        """
        self._send_rpc(kill_session(session_id))

    def close_session(self):
        """Send a ``<close-session>`` request"""
        self._send_rpc(close_session())

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
        self._send_rpc(rpc_xml)

    def validate(self, source):
        """Send a ``<validate>`` request

        :param str source: The datastore to validate
        """
        self._send_rpc(validate(source))

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
        (msg, _) = self._send_rpc(make_rpc(from_ele(rpc)))
        return RPCReply(msg)

    def delete_config(self, target):
        """Send a ``<delete-config>`` request

        :param str target: The datastore to delete
        """
        self._send_rpc(delete_config(target))


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

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


class Manager:
    """A helper class for performing common NETCONF operations

    This class attempts to be API compatible with the manager object
    from the original ncclient.

    This class is also a context manager and can be used with `with`
    statements to automatically close the underlying session.

    :ivar float timeout: Duration in seconds to wait for a reply

    :ivar session: The underlying
                   :class:`netconf_client.session.Session` connected
                   to the server

    """

    def __init__(self, session, timeout=120):
        """Construct a new Manager object

        :param session: The low-level NETCONF session to use for requests
        :type session: :class:`netconf_client.session.Session`

        :param float timeout: Duration in seconds to wait for replies
        """
        self.timeout = timeout
        self.session = session

    def __enter__(self):
        return self

    def __exit__(self, a, b, c):
        self.session.__exit__(a, b, c)

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
        f = self.session.send_rpc(
            edit_config(config, target, default_operation, test_option, error_option)
        )
        f.result(timeout=self.timeout)

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
        f = self.session.send_rpc(
            get(filter=convert_filter(filter), with_defaults=with_defaults)
        )
        (raw, ele) = f.result(timeout=self.timeout)
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
        f = self.session.send_rpc(
            get_config(
                source=source,
                filter=convert_filter(filter),
                with_defaults=with_defaults,
            )
        )
        (raw, ele) = f.result(timeout=self.timeout)
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
        f = self.session.send_rpc(
            copy_config(target=target, source=source, with_defaults=with_defaults)
        )
        f.result(timeout=self.timeout)

    def discard_changes(self):
        """Send a ``<discard-changes>`` request"""
        f = self.session.send_rpc(discard_changes())
        f.result(timeout=self.timeout)

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
        f = self.session.send_rpc(
            commit(
                confirmed=confirmed,
                confirm_timeout=confirm_timeout,
                persist=persist,
                persist_id=persist_id,
            )
        )
        f.result(timeout=self.timeout)

    def lock(self, target):
        """Send a ``<lock>`` request

        :param str target: The datastore to be locked
        """
        f = self.session.send_rpc(lock(target))
        f.result(timeout=self.timeout)

    def unlock(self, target):
        """Send an ``<unlock>`` request

        :param str target: The datastore to be unlocked
        """
        f = self.session.send_rpc(unlock(target))
        f.result(timeout=self.timeout)

    def kill_session(self, session_id):
        """Send a ``<kill-session>`` request

        :param int session_id: The session to be killed
        """
        f = self.session.send_rpc(kill_session(session_id))
        f.result(timeout=self.timeout)

    def close_session(self):
        """Send a ``<close-session>`` request"""
        f = self.session.send_rpc(close_session())
        f.result(timeout=self.timeout)

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
        f = self.session.send_rpc(
            create_subscription(
                stream=stream, filter=filter, start_time=start_time, stop_time=stop_time
            )
        )
        f.result(timeout=self.timeout)

    def validate(self, source):
        """Send a ``<validate>`` request

        :param str source: The datastore to validate
        """
        f = self.session.send_rpc(validate(source))
        f.result(timeout=self.timeout)

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
        f = self.session.send_rpc(make_rpc(from_ele(rpc)))
        (msg, _) = f.result(timeout=self.timeout)
        return RPCReply(msg)

    def delete_config(self, target):
        """Send a ``<delete-config>`` request

        :param str target: The datastore to delete
        """
        f = self.session.send_rpc(delete_config(target))
        f.result(timeout=self.timeout)


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

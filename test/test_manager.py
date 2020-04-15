import uuid
from socket import error as socket_error
from concurrent.futures import Future, CancelledError, TimeoutError
import logging
import re
from mock import patch
from lxml import etree
from six.moves.queue import Empty
import pytest

from netconf_client.ncclient import Manager, convert_filter, from_ele, to_ele

RPC_REPLY_DATA = """
<rpc-reply message-id="fake-id"
     xmlns="urn:ietf:params:xml:ns:netconf:base:1.0">
  <data>bar</data>
</rpc-reply>
"""


class LogRecorder(logging.Filter):
    """helper class, doesn't really want to log, only capture the log items"""

    def __init__(self):
        logging.Filter.__init__(self)
        self.records = []

    def clear(self):
        self.records = []

    def count(self):
        return len(self.records)

    def check_content(self, funcname, content):
        """checks expected number of recorded log items and their contents"""
        if not content:
            return True

        assert len(content) == self.count()

        for (rec, cont) in zip(self.records, content):
            # rec: dict: current record
            # cont: list: sequence of strings all contained in r["formatted_message"]

            scope = rec.get("name")
            assert scope is not None and scope == "netconf_client.manager"

            level = rec.get("levelname")
            assert level is not None and level == "DEBUG"

            func = rec.get("ncclient.Manager.funcname")
            assert func is not None and func == funcname

            msg = rec.get("formatted_message")
            assert msg is not None
            for s in cont:
                assert re.search(s, msg)

        return True

    def filter(self, record):
        """filter hook, overwrites logging.Filter.filter()"""

        entry = {}
        try:
            entry = record.__dict__
            msg = entry.get("msg")
            args = entry.get("args")
            if msg and args:
                # store fully formatted log message
                entry["formatted_message"] = msg % (args)
        except AttributeError:
            pass

        self.records.append(entry)
        return False  # don't really log anything, recording only


# install a log recorder
log_recorder = LogRecorder()
Manager.logger().addFilter(log_recorder)


class LogSentry:
    def __init__(self, log_enabled):
        log_recorder.clear()
        Manager.logger().setLevel(logging.DEBUG if log_enabled else logging.NOTSET)
        assert Manager.logger().isEnabledFor(logging.DEBUG) == log_enabled

    def __enter__(self):
        return self

    def __exit__(self, a, b, c):
        log_recorder.clear()
        Manager.logger().setLevel(logging.NOTSET)


def test_manager_lifecycle(session):
    with Manager(session, timeout=1) as mgr:
        assert mgr.timeout == 1
        assert mgr.log_id is None
        assert mgr.session_id() == 4711
    assert session.closed


def test_manager_lifecycle_with_id(session):
    session.set_session_id(4712)
    with Manager(session, log_id="Raspberry Pi 3") as mgr:
        assert mgr.timeout == 120  # default timeout
        assert mgr.log_id == "Raspberry Pi 3"
        assert mgr.session_id() == 4712
    assert session.closed


# remark: we only can check some fragments of the "pretty" log contents
# because the etree formatter from lmtree package might reorder XML tags.
@pytest.mark.parametrize(
    "log_enabled,log_id,log_funcname,log_content",
    [
        (False, None, None, None),
        (
            True,
            None,
            "edit_config",
            [
                [
                    "NC Request:",
                    "<edit-config xmlns:nc",
                    "<default-operation>merge</default-operation>",
                    "</edit-config>",
                ],
                [
                    r"NC Failure \(\d\.\d+ sec\)\n",
                    "Cause: RPC returned without result",
                ],
            ],
        ),
        (
            True,
            "Raspi-2",
            "edit_config",
            [
                [
                    "NC Request => Raspi-2:",
                    "<edit-config xmlns:nc",
                    "<default-operation>merge</default-operation>",
                    "</edit-config>",
                ],
                [
                    r"NC Failure <= Raspi-2 \(\d\.\d+ sec\)\n",
                    "Cause: RPC returned without result",
                ],
            ],
        ),
    ],
    ids=["logging disabled", "logging enabled", "logging w/ ID"],
)
def test_edit_config(session, fake_id, log_enabled, log_id, log_funcname, log_content):
    session.replies.append(None)

    with LogSentry(log_enabled), Manager(session, timeout=1, log_id=log_id) as mgr:
        mgr.edit_config(
            config="<config>foo</config>",
            target="candidate",
            default_operation="merge",
            test_option="set-only",
            error_option="rollback-on-error",
        )
        assert session.sent[0] == uglify(
            """
            <rpc message-id="fake-id" xmlns="urn:ietf:params:xml:ns:netconf:base:1.0">
              <edit-config xmlns:nc="urn:ietf:params:xml:ns:netconf:base:1.0">
                <target>
                  <candidate/>
                </target>
                <default-operation>merge</default-operation>
                <test-option>set-only</test-option>
                <error-option>rollback-on-error</error-option>
                <config>foo</config>
              </edit-config>
            </rpc>
            """
        )
        assert log_recorder.check_content(log_funcname, log_content)


@pytest.mark.parametrize(
    "log_id,log_local_ip,log_peer_ip,log_content",
    [
        # no IDs
        (
            None,
            None,
            None,
            [
                ["NC Request:\n", "<get xmlns:nc", "<filter>foo</filter>", "</get>"],
                [
                    r"NC Response \(\d\.\d+ sec\):\n",
                    "<rpc-reply ",
                    "<data>bar</data>",
                    "</rpc-reply>",
                ],
            ],
        ),
        # log ID only
        (
            "Raspi-4",
            None,
            None,
            [
                [
                    "NC Request => Raspi-4:\n",
                    "<get xmlns:nc",
                    "<filter>foo</filter>",
                    "</get>",
                ],
                [
                    r"NC Response <= Raspi-4 \(\d\.\d+ sec\):\n",
                    "<rpc-reply ",
                    "<data>bar</data>",
                    "</rpc-reply>",
                ],
            ],
        ),
        # connection IP addresses only
        (
            None,
            "1.2.3.4",
            "5.6.7.8",
            [
                [
                    r"NC Request 1\.2\.3\.4 => 5\.6\.7\.8:\n",
                    "<get xmlns:nc",
                    "<filter>foo</filter>",
                    "</get>",
                ],
                [
                    r"NC Response 1\.2\.3\.4 <= 5\.6\.7\.8 \(\d\.\d+ sec\):\n",
                    "<rpc-reply ",
                    "<data>bar</data>",
                    "</rpc-reply>",
                ],
            ],
        ),
        # log ID and connection IP addresses
        (
            "Raspi-4",
            "1.2.3.4",
            "5.6.7.8",
            [
                [
                    r"NC Request \(1\.2\.3\.4\) => Raspi-4 \(5\.6\.7\.8\):\n",
                    "<get xmlns:nc",
                    "<filter>foo</filter>",
                    "</get>",
                ],
                [
                    r"NC Response \(1\.2\.3\.4\) <= Raspi-4 \(5\.6\.7\.8\) \(\d\.\d+ sec\):\n",
                    "<rpc-reply ",
                    "<data>bar</data>",
                    "</rpc-reply>",
                ],
            ],
        ),
    ],
    ids=["no IDs", "w/ log ID", "w/ IP addr", "w/ log ID+IP addr"],
)
def test_get(fake_id, log_id, log_local_ip, log_peer_ip, log_content):
    with LogSentry(True), MockSession(
        [], log_local_ip, log_peer_ip
    ) as session, Manager(session, timeout=1, log_id=log_id) as mgr:
        session.replies.append((RPC_REPLY_DATA, etree.fromstring(RPC_REPLY_DATA)))
        r = mgr.get(filter="<filter>foo</filter>", with_defaults="explicit")
        assert session.sent[0] == uglify(
            """
            <rpc message-id="fake-id" xmlns="urn:ietf:params:xml:ns:netconf:base:1.0">
              <get xmlns:nc="urn:ietf:params:xml:ns:netconf:base:1.0">
                <filter>foo</filter>
                <with-defaults xmlns="urn:ietf:params:xml:ns:yang:ietf-netconf-with-defaults">
                  explicit
                </with-defaults>
              </get>
            </rpc>
            """
        )
        assert r.data_ele.text == "bar"
        assert log_recorder.check_content("get", log_content)


def test_get_config(session, fake_id):
    session.replies.append((RPC_REPLY_DATA, etree.fromstring(RPC_REPLY_DATA)))
    with Manager(session, timeout=1) as mgr:
        r = mgr.get_config(
            source="candidate", filter="<filter>foo</filter>", with_defaults="explicit"
        )
        assert session.sent[0] == uglify(
            """
            <rpc message-id="fake-id" xmlns="urn:ietf:params:xml:ns:netconf:base:1.0">
              <get-config xmlns:nc="urn:ietf:params:xml:ns:netconf:base:1.0">
                <source>
                  <candidate/>
                </source>
                <filter>foo</filter>
                <with-defaults xmlns="urn:ietf:params:xml:ns:yang:ietf-netconf-with-defaults">
                  explicit
                </with-defaults>
              </get-config>
            </rpc>
            """
        )
        assert r.data_ele.text == "bar"


def test_copy_config(session, fake_id):
    session.replies.append(None)
    with Manager(session, timeout=1) as mgr:
        mgr.copy_config(source="running", target="startup", with_defaults="explicit")
        assert session.sent[0] == uglify(
            """
            <rpc message-id="fake-id" xmlns="urn:ietf:params:xml:ns:netconf:base:1.0">
              <copy-config>
                <target>
                  <startup/>
                </target>
                <source>
                  <running/>
                </source>
                <with-defaults xmlns="urn:ietf:params:xml:ns:yang:ietf-netconf-with-defaults">
                  explicit
                </with-defaults>
              </copy-config>
            </rpc>
            """
        )


def test_discard_changes(session, fake_id):
    session.replies.append(None)
    with Manager(session, timeout=1) as mgr:
        mgr.discard_changes()
        assert session.sent[0] == uglify(
            """
            <rpc message-id="fake-id" xmlns="urn:ietf:params:xml:ns:netconf:base:1.0">
              <discard-changes/>
            </rpc>
            """
        )


def test_commit(session, fake_id):
    session.replies.append(None)
    with Manager(session, timeout=1) as mgr:
        mgr.commit(confirmed=True, confirm_timeout=7, persist="foo", persist_id="bar")
        assert session.sent[0] == uglify(
            """
            <rpc message-id="fake-id" xmlns="urn:ietf:params:xml:ns:netconf:base:1.0">
              <commit>
                <confirmed/>
                <confirm-timeout>7</confirm-timeout>
                <persist>foo</persist>
                <persist-id>bar</persist-id>
              </commit>
            </rpc>
            """
        )


def test_lock(session, fake_id):
    session.replies.append(None)
    with Manager(session, timeout=1) as mgr:
        mgr.lock(target="startup")
        assert session.sent[0] == uglify(
            """
            <rpc message-id="fake-id" xmlns="urn:ietf:params:xml:ns:netconf:base:1.0">
              <lock>
                <target>
                  <startup/>
                </target>
              </lock>
            </rpc>
            """
        )


def test_unlock(session, fake_id):
    session.replies.append(None)
    with Manager(session, timeout=1) as mgr:
        mgr.unlock(target="startup")
        assert session.sent[0] == uglify(
            """
            <rpc message-id="fake-id" xmlns="urn:ietf:params:xml:ns:netconf:base:1.0">
              <unlock>
                <target>
                  <startup/>
                </target>
              </unlock>
            </rpc>
            """
        )


def test_kill_session(session, fake_id):
    session.replies.append(None)
    with Manager(session, timeout=1) as mgr:
        mgr.kill_session(session_id=7)
        assert session.sent[0] == uglify(
            """
            <rpc message-id="fake-id" xmlns="urn:ietf:params:xml:ns:netconf:base:1.0">
              <kill-session>
                <session-id>7</session-id>
              </kill-session>
            </rpc>
            """
        )


def test_close_session(session, fake_id):
    session.replies.append(None)
    with Manager(session, timeout=1) as mgr:
        mgr.close_session()
        assert session.sent[0] == uglify(
            """
            <rpc message-id="fake-id" xmlns="urn:ietf:params:xml:ns:netconf:base:1.0">
              <close-session/>
            </rpc>
            """
        )


def test_create_subscription(session, fake_id):
    session.replies.append(None)
    with Manager(session, timeout=1) as mgr:
        mgr.create_subscription(
            stream="NETCONF",
            filter="<filter>foo</filter>",
            start_time="noon",
            stop_time="midnight",
        )
        assert session.sent[0] == uglify(
            """
            <rpc message-id="fake-id" xmlns="urn:ietf:params:xml:ns:netconf:base:1.0">
              <create-subscription xmlns="urn:ietf:params:xml:ns:netconf:notification:1.0">
                <stream>NETCONF</stream>
                <filter>foo</filter>
                <startTime>noon</startTime>
                <stopTime>midnight</stopTime>
              </create-subscription>
            </rpc>
            """
        )


def test_validate_datastore(session, fake_id):
    session.replies.append(None)
    with Manager(session, timeout=1) as mgr:
        mgr.validate(source="running")
        assert session.sent[0] == uglify(
            """
            <rpc message-id="fake-id" xmlns="urn:ietf:params:xml:ns:netconf:base:1.0">
              <validate>
                <source>
                  <running/>
                </source>
              </validate>
            </rpc>
            """
        )


def test_validate_config(session, fake_id):
    session.replies.append(None)
    with Manager(session, timeout=1) as mgr:
        mgr.validate(source=etree.fromstring("<config>foo</config>"))
        assert session.sent[0] == uglify(
            """
            <rpc message-id="fake-id" xmlns="urn:ietf:params:xml:ns:netconf:base:1.0">
              <validate>
                <source>
                  <config>foo</config>
                </source>
              </validate>
            </rpc>
            """
        )


def test_delete_config(session, fake_id):
    session.replies.append(None)
    with Manager(session, timeout=1) as mgr:
        mgr.delete_config(target="running")
        assert session.sent[0] == uglify(
            """
            <rpc message-id="fake-id" xmlns="urn:ietf:params:xml:ns:netconf:base:1.0">
              <delete-config>
                <target>
                  <running/>
                </target>
              </delete-config>
            </rpc>
            """
        )


def test_dispatch(session, fake_id):
    session.replies.append((RPC_REPLY_DATA, etree.fromstring(RPC_REPLY_DATA)))
    with LogSentry(True), Manager(session, timeout=1) as mgr:
        reply = mgr.dispatch("<data>pie test</data>")
        assert session.sent[0] == uglify(
            """
            <rpc message-id="fake-id" xmlns="urn:ietf:params:xml:ns:netconf:base:1.0">
              <data>pie test</data>
            </rpc>
            """
        )
        assert uglify(reply.xml) == uglify(
            """
            <rpc-reply message-id="fake-id"
              xmlns="urn:ietf:params:xml:ns:netconf:base:1.0">
                <data>bar</data>
            </rpc-reply>
            """
        )
        assert log_recorder.check_content(
            "dispatch",
            [
                ["NC Request:\n", "<rpc xmlns", "<data>pie test</data>", "</rpc>"],
                [
                    r"NC Response \(\d\.\d+ sec\):\n",
                    "<rpc-reply",
                    "<data>bar</data>",
                    "</rpc-reply>",
                ],
            ],
        )


def test_take_notification_default(session):
    session.set_notifications(msg="message", ele="element")
    with Manager(session) as mgr:
        notification = mgr.take_notification()
        assert notification.notification_ele == "element"
        assert notification.notification_xml == "message"
        assert session.notifications.block is True
        assert session.notifications.timeout is None


def test_take_notification(session):
    session.set_notifications(msg="message", ele="element")
    with Manager(session) as mgr:
        notification = mgr.take_notification(block=False, timeout=1.23)
        assert notification.notification_ele == "element"
        assert notification.notification_xml == "message"
        assert session.notifications.block is False
        assert session.notifications.timeout == 1.23


def test_take_notification_empty(session):
    with Manager(session) as mgr:
        notification = mgr.take_notification()
        assert notification is None


@pytest.mark.parametrize(
    "log_enabled,session_exception,log_content",
    [
        (False, socket_error, None),
        (
            True,
            CancelledError,
            [
                [
                    "NC Request => bad device:\n",
                    "<get xmlns:nc",
                    "<filter>foo</filter>",
                    "</get>",
                ],
                [
                    r"NC Failure <= bad device \(\d\.\d+ sec\)\n",
                    "Cause: RPC cancelled",
                ],
            ],
        ),
        (
            True,
            TimeoutError,
            [
                [
                    "NC Request => bad device:\n",
                    "<get xmlns:nc",
                    "<filter>foo</filter>",
                    "</get>",
                ],
                [
                    r"NC Failure <= bad device \(\d\.\d+ sec\)\n",
                    r"Cause: RPC timeout \(max\. 10 seconds\)",
                ],
            ],
        ),
        (
            True,
            ValueError,
            [
                [
                    "NC Request => bad device:\n",
                    "<get xmlns:nc",
                    "<filter>foo</filter>",
                    "</get>",
                ],
                [
                    r"NC Failure <= bad device \(\d\.\d+ sec\)\n",
                    "Cause: RPC exception: " + str(ValueError()),
                ],
            ],
        ),
    ],
    ids=["no logging", "CancelledError", "TimeoutError", "any"],
)
def test_exceptions(fake_id, log_enabled, session_exception, log_content):
    with LogSentry(log_enabled), MockSession([],) as session, Manager(
        session, timeout=10, log_id="bad device"
    ) as mgr:
        session.replies.append((RPC_REPLY_DATA, etree.fromstring(RPC_REPLY_DATA)))
        session.set_exception(session_exception())

        caught = None
        try:
            r = mgr.get(filter="<filter>foo</filter>", with_defaults="explicit")
        except Exception as e:
            caught = e

        assert isinstance(caught, session_exception)
        assert log_recorder.check_content("get", log_content)


@pytest.mark.parametrize(
    "inp,result",
    [
        (None, None),
        (("subtree", "data"), "<filter>data</filter>"),
        ("as-it-is", "as-it-is"),
    ],
    ids=["None", "subtree", "pass-through"],
)
def test_convert_filter(inp, result):
    assert convert_filter(inp) == result


def test_convert_filter_unimplemented():
    caught = None
    try:
        convert_filter(("subway", "restaurant"))
    except Exception as e:
        caught = e
    assert isinstance(caught, NotImplementedError)
    assert str(caught) == "Unimplemented filter type subway"


@pytest.mark.parametrize(
    "inp,result",
    [("as-it-is", "as-it-is"), (etree.Element("data"), "<data/>"),],
    ids=["pass-through", "Element"],
)
def test_from_ele(inp, result):
    assert from_ele(inp) == result


@pytest.mark.parametrize(
    "inp,result",
    [("<root>data</root>", "root"), (etree.Element("data"), "data"),],
    ids=["convert", "Element"],
)
def test_to_ele(inp, result):
    ele = to_ele(inp)
    assert ele.tag == result


class MockSocket:
    def __init__(self, local_ip, peer_ip):
        self.local_ip = local_ip
        self.peer_ip = peer_ip
        self.sock = self

    def getsockname(self):
        if not self.local_ip:
            raise socket_error()
        return (self.local_ip, None)  # pair(ip addr, port num)

    def getpeername(self):
        if not self.peer_ip:
            raise socket_error()
        return (self.peer_ip, None)


class MockNotifications:
    def __init__(self):
        self.block = None
        self.timeout = 1
        self.msg = None
        self.ele = None

    def set(self, msg, ele):
        self.msg = msg
        self.ele = ele

    def get(self, block, timeout):
        if self.msg is None and self.ele is None:
            raise Empty
        self.block = block
        self.timeout = timeout
        return (self.msg, self.ele)


class MockSession:
    def __init__(self, replies, local_ip=None, peer_ip=None):
        self.sent = []
        self.replies = replies
        self.closed = False
        self.sock = MockSocket(local_ip, peer_ip)
        self.id = 4711
        self.exception = None
        self.notifications = MockNotifications()

    def __enter__(self):
        return self

    def __exit__(self, _, __, ___):
        self.closed = True

    def send_rpc(self, rpc):
        self.sent.append(rpc)
        v = self.replies[0]
        self.replies = self.replies[1:]
        f = Future()
        f.set_result(v)
        if self.exception:
            f.set_exception(self.exception)
        return f

    def session_id(self):
        return self.id

    def set_session_id(self, session_id):
        self.id = session_id

    def set_exception(self, exception):
        self.exception = exception

    def set_notifications(self, msg, ele):
        self.notifications.set(msg, ele)


@pytest.fixture()
def session():
    return MockSession([])


def uglify(s):
    return "".join([x.strip() for x in s.splitlines()]).encode("utf-8")


@pytest.fixture()
def fake_id():
    with patch.object(uuid, "uuid4", return_value="fake-id"):
        yield

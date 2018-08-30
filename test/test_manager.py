import uuid
from concurrent.futures import Future
from mock import patch
from lxml import etree
import pytest

from netconf_client.ncclient import Manager

RPC_REPLY_DATA = """
<rpc-reply message-id="fake-id"
     xmlns="urn:ietf:params:xml:ns:netconf:base:1.0">
  <data>bar</data>
</rpc-reply>
"""


def test_manager_lifecycle(session):
    with Manager(session, timeout=1):
        pass
    assert session.closed


def test_edit_config(session, fake_id):
    session.replies.append(None)
    with Manager(session, timeout=1) as mgr:
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


def test_get(session, fake_id):
    session.replies.append((RPC_REPLY_DATA, etree.fromstring(RPC_REPLY_DATA)))
    with Manager(session, timeout=1) as mgr:
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


class MockSession:
    def __init__(self, replies):
        self.sent = []
        self.replies = replies
        self.closed = False

    def send_rpc(self, rpc):
        self.sent.append(rpc)
        v = self.replies[0]
        self.replies = self.replies[1:]
        f = Future()
        f.set_result(v)
        return f

    def __exit__(self, _, __, ___):
        self.closed = True


@pytest.fixture()
def session():
    return MockSession([])


def uglify(s):
    return "".join([x.strip() for x in s.splitlines()]).encode("utf-8")


@pytest.fixture()
def fake_id():
    with patch.object(uuid, "uuid4", return_value="fake-id"):
        yield

from six.moves.queue import Queue
import pytest

from netconf_client.session import Session, frame_message_11
from netconf_client.constants import DEFAULT_HELLO, DELIMITER_10
from netconf_client.error import RpcError, SessionClosedException

from common import RPC_ERROR_WITHOUT_MSG


SERVER_HELLO = b"""
  <hello xmlns="urn:ietf:params:xml:ns:netconf:base:1.0">
    <capabilities>
      <capability>urn:ietf:params:netconf:base:1.1</capability>
      <capability>http://example.com/foo</capability>
    </capabilities>
    <session-id>4</session-id>
  </hello>
"""

SERVER_HELLO_10 = b"""
  <hello xmlns="urn:ietf:params:xml:ns:netconf:base:1.0">
    <capabilities>
      <capability>http://example.com/foo</capability>
    </capabilities>
    <session-id>4</session-id>
  </hello>
"""

TEST_RPC = b"""
  <rpc message-id="101" xmlns="urn:ietf:params:xml:ns:netconf:base:1.0">
    <some-method/>
  </rpc>
"""

TEST_RPC_REPLY = b"""
<rpc-reply message-id="101"
     xmlns="urn:ietf:params:xml:ns:netconf:base:1.0"
     xmlns:ex="http://example.net/content/1.0"
     ex:user-id="fred">
  <data />
</rpc-reply>
"""

TEST_NOTIFICATION = b"""
<notification
   xmlns="urn:ietf:params:xml:ns:netconf:notification:1.0">
   <eventTime>2007-07-08T00:01:00Z</eventTime>
   <event xmlns="http://example.com/event/1.0">
      <eventClass>fault</eventClass>
      <reportingEntity>
          <card>Ethernet0</card>
      </reportingEntity>
      <severity>major</severity>
    </event>
</notification>
"""


class MockSock:
    def __init__(self, recvs):
        self.recvs = Queue()
        for r in recvs:
            self.recvs.put(r)

        self.sent = []
        self.closed = False

    def sendall(self, b):
        self.sent.append(b)

    def recv(self, _=-1):
        if self.closed:
            raise Exception()

        return self.recvs.get()

    def close(self):
        self.closed = True
        self.recvs.put(b"")


def test_encoding_10():
    s = MockSock([SERVER_HELLO_10 + DELIMITER_10 + TEST_RPC_REPLY + DELIMITER_10])
    with Session(s) as session:
        assert session.server_hello == SERVER_HELLO_10
        assert session.session_id == 4
        assert session.server_capabilities == ["http://example.com/foo"]
        assert session.client_capabilities == ["urn:ietf:params:netconf:base:1.1"]
        assert session.mode == "1.0"

        s.sent = []
        session.send_msg(TEST_RPC)
        assert s.sent == [TEST_RPC + DELIMITER_10]

        assert session.unknown_recvq.get(timeout=1)[0] == TEST_RPC_REPLY

    assert s.closed


def test_encoding_11():
    s = MockSock([SERVER_HELLO + DELIMITER_10, frame_message_11(TEST_RPC_REPLY)])
    with Session(s) as session:
        assert s.sent == [DEFAULT_HELLO + DELIMITER_10]
        s.sent = []
        assert not s.closed

        assert session.server_hello == SERVER_HELLO
        assert session.session_id == 4
        assert session.server_capabilities == [
            "urn:ietf:params:netconf:base:1.1",
            "http://example.com/foo",
        ]
        assert session.client_capabilities == ["urn:ietf:params:netconf:base:1.1"]
        assert session.mode == "1.1"

        session.send_msg(TEST_RPC)
        assert s.sent == [b"\n#102\n" + TEST_RPC + b"\n##\n"]

        assert session.unknown_recvq.get(timeout=1)[0] == TEST_RPC_REPLY

    assert s.closed


def test_request_response():
    s = MockSock([SERVER_HELLO + DELIMITER_10])
    with Session(s) as session:
        response_f = session.send_rpc(TEST_RPC)

        s.recvs.put(
            frame_message_11(TEST_NOTIFICATION)
            + frame_message_11(TEST_RPC_REPLY)
            + frame_message_11(TEST_NOTIFICATION)
        )

        assert response_f.result()[0] == TEST_RPC_REPLY
        assert session.notifications.get(timeout=1)[0] == TEST_NOTIFICATION
        assert session.notifications.get(timeout=1)[0] == TEST_NOTIFICATION


def test_request_error_response():
    s = MockSock([SERVER_HELLO + DELIMITER_10])
    with Session(s) as session:
        response_f = session.send_rpc(TEST_RPC)
        response_f2 = session.send_rpc(TEST_RPC)

        s.recvs.put(frame_message_11(RPC_ERROR_WITHOUT_MSG))

        with pytest.raises(RpcError):
            response_f.result()

        # And then ensure a regular message can still get through
        s.recvs.put(frame_message_11(TEST_RPC_REPLY))
        assert response_f2.result()[0] == TEST_RPC_REPLY


def test_session_close_breaks_promises():
    s = MockSock([SERVER_HELLO + DELIMITER_10])
    with Session(s) as session:
        response_f = session.send_rpc(TEST_RPC)

    with pytest.raises(SessionClosedException):
        response_f.result()

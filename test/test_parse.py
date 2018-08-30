from netconf_client.parser import parse_messages


class MockStream:
    def __init__(self, chunks):
        self.chunks = chunks

    def recv(self, _=-1):
        assert self.chunks, "End of stream"
        v = self.chunks[0]
        self.chunks = self.chunks[1:]
        return v


def test_single_message_single_chunk_10():
    g = parse_messages(MockStream([b"Foo]]>]]>"]), "1.0")
    assert next(g) == b"Foo"


def test_single_message_multiple_chunks_10():
    g = parse_messages(MockStream([b"Foo", b"]]>]]>"]), "1.0")
    assert next(g) == b"Foo"


def test_multiple_messages_single_chunk_10():
    g = parse_messages(MockStream([b"Foo]]>]]>", b"Bar]]>]]>"]), "1.0")
    assert next(g) == b"Foo"
    assert next(g) == b"Bar"


def test_single_message_single_chunk_11():
    g = parse_messages(MockStream([b"\n#3\nFoo\n##\n"]), "1.1")
    assert next(g) == b"Foo"


def test_single_message_multiple_chunks_11():
    g = parse_messages(MockStream([b"\n#3\nFoo\n#4\nBars\n##\n"]), "1.1")
    assert next(g) == b"FooBars"


def test_multiple_messages_multiple_chunks_11():
    g = parse_messages(MockStream([b"\n#3\nFoo\n#4\nBars\n##\n\n#3\nBaz\n##\n"]), "1.1")
    assert next(g) == b"FooBars"
    assert next(g) == b"Baz"

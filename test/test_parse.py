import pytest
from netconf_client.parser import parse_messages
from netconf_client.error import NetconfProtocolError


class EndOfStream(Exception):
    pass


class MockStream:
    def __init__(self, chunks):
        self.chunks = chunks

    def recv(self, _=-1):
        if not self.chunks:
            raise EndOfStream()
        v = self.chunks[0]
        self.chunks = self.chunks[1:]
        return v


def test_single_message_single_chunk_10():
    g = parse_messages(MockStream([b"Foo]]>]]>"]), "1.0")
    assert next(g) == b"Foo"
    with pytest.raises(EndOfStream):
        next(g)


def test_single_message_multiple_chunks_10():
    g = parse_messages(MockStream([b"Foo", b"]]>]]>"]), "1.0")
    assert next(g) == b"Foo"
    with pytest.raises(EndOfStream):
        next(g)


def test_multiple_messages_single_chunk_10():
    g = parse_messages(MockStream([b"Foo]]>]]>", b"Bar]]>]]>"]), "1.0")
    assert next(g) == b"Foo"
    assert next(g) == b"Bar"
    with pytest.raises(EndOfStream):
        next(g)


def test_single_message_10_fragmented_msg_1():
    g = parse_messages(MockStream([b"Foo", b"Bar", b"]]>]]>"]), "1.0")
    assert next(g) == b"FooBar"
    with pytest.raises(EndOfStream):
        next(g)


def test_single_message_10_fragmented_msg_2():
    g = parse_messages(MockStream([b"got a longer ", b"message", b"]]>]]>"]), "1.0")
    assert next(g) == b"got a longer message"
    with pytest.raises(EndOfStream):
        next(g)


def test_single_message_10_fragmented_msg_3():
    g = parse_messages(MockStream([b"partly ]]>]] delimiter", b"]]>]]>"]), "1.0")
    assert next(g) == b"partly ]]>]] delimiter"
    with pytest.raises(EndOfStream):
        next(g)


def test_single_message_10_fragmented_msg_4():
    g = parse_messages(MockStream([b"partly ]]>]]", b" delimiter]]>]]>"]), "1.0")
    assert next(g) == b"partly ]]>]] delimiter"
    with pytest.raises(EndOfStream):
        next(g)


def test_single_message_10_fragmented_delim_begin():
    g = parse_messages(MockStream([b"Foo]", b"]>]]>"]), "1.0")
    assert next(g) == b"Foo"
    with pytest.raises(EndOfStream):
        next(g)


def test_single_message_10_fragmented_delim_mid():
    g = parse_messages(MockStream([b"Foo]]>", b"]]>"]), "1.0")
    assert next(g) == b"Foo"
    with pytest.raises(EndOfStream):
        next(g)


def test_single_message_10_fragmented_delim_end():
    g = parse_messages(MockStream([b"Foo]]>]", b"]>"]), "1.0")
    assert next(g) == b"Foo"
    with pytest.raises(EndOfStream):
        next(g)


def test_multiple_messages_10_fragmented_delim():
    g = parse_messages(MockStream([b"Foo]", b"]>]]", b">", b"Ba", b"r]]>]]>"]), "1.0")
    assert next(g) == b"Foo"
    assert next(g) == b"Bar"
    with pytest.raises(EndOfStream):
        next(g)


def test_unexpected_end_of_stream_10():
    g = parse_messages(MockStream([b"Any data, but no delimiter HERE"]), "1.0")
    with pytest.raises(EndOfStream):
        next(g)


# ---------------------------------------------------------------------------------------


def test_single_message_single_chunk_11():
    g = parse_messages(MockStream([b"\n#3\nFoo\n##\n"]), "1.1")
    assert next(g) == b"Foo"
    with pytest.raises(EndOfStream):
        next(g)


def test_single_message_multiple_chunks_11():
    g = parse_messages(MockStream([b"\n#3\nFoo\n#4\nBars\n##\n"]), "1.1")
    assert next(g) == b"FooBars"
    with pytest.raises(EndOfStream):
        next(g)


def test_multiple_11_fragmented_1():
    g = parse_messages(MockStream([b"\n#3", b"\nFo", b"o\n#4\nBars\n", b"##\n"]), "1.1")
    assert next(g) == b"FooBars"
    with pytest.raises(EndOfStream):
        next(g)


def test_multiple_11_fragmented_2():
    g = parse_messages(
        MockStream(
            [
                b"\n#3",
                b"\nFo",
                b"o\n#4\nBars",
                b"\n#",
                b"#\n\n",
                b"#7\nBazooka\n##",
                b"\n",
            ]
        ),
        "1.1",
    )
    assert next(g) == b"FooBars"
    assert next(g) == b"Bazooka"
    with pytest.raises(EndOfStream):
        next(g)


def test_multiple_11_fragmented_3():
    g = parse_messages(
        MockStream(
            [
                b"\n#17\nabcdefghijklmnopq",
                b"\n#13\nrstunvxyzABCD\n#10",
                b"\nEFGHIJKLMN\n##\n",
            ]
        ),
        "1.1",
    )
    assert next(g) == b"abcdefghijklmnopq" + b"rstunvxyzABCD" + b"EFGHIJKLMN"
    with pytest.raises(EndOfStream):
        next(g)


def test_multiple_messages_multiple_chunks_11():
    g = parse_messages(MockStream([b"\n#3\nFoo\n#4\nBars\n##\n\n#3\nBaz\n##\n"]), "1.1")
    assert next(g) == b"FooBars"
    assert next(g) == b"Baz"
    with pytest.raises(EndOfStream):
        next(g)


def test_unexpected_end_of_stream_11_2():
    g = parse_messages(
        MockStream([b"\n#200\nAny data, but no next chunk or delimiter HERE "]), "1.1"
    )
    with pytest.raises(EndOfStream):
        next(g)


def test_unexpected_end_of_stream_11_3():
    g = parse_messages(MockStream([b"\n#8\nAny data"]), "1.1")
    with pytest.raises(EndOfStream):
        next(g)


def test_unexpected_end_of_stream_11_4():
    g = parse_messages(MockStream([b"\n#8\nAny data\n#200\n"]), "1.1")
    with pytest.raises(EndOfStream):
        next(g)


# ---------------------------------------------------------------------------------------


def test_version_transition_simple():
    g = parse_messages(
        MockStream(
            [
                # version 1.0
                b"Hello]]>]]>",
                # version 1.1
                b"\n#3\n" + b"Foo" + b"\n#4\n" + b"Bars" + b"\n##\n\n",
                b"#8\n" + b"Bazookas" + b"\n##\n",
            ]
        ),
        "1.0",
    )
    assert next(g) == b"Hello"
    assert g.send("1.1") == b"FooBars"
    assert g.send("1.1") == b"Bazookas"
    with pytest.raises(EndOfStream):
        next(g)


def test_version_transition_fragmented():
    g = parse_messages(
        MockStream(
            [
                # 1st recv(): version 1.0 plus fragments from version 1.1 message
                b"Hello]]>]]>" + b"\n#3\n" + b"Foo",
                # 2nd and 3rd recv(): rest of version 1.1 messages
                b"\n#4\n" + b"Bars" + b"\n##\n\n",
                b"#8\n" + b"Bazookas" + b"\n##\n",
            ]
        ),
        "1.0",
    )
    assert next(g) == b"Hello"
    assert g.send("1.1") == b"FooBars"
    assert g.send("1.1") == b"Bazookas"
    with pytest.raises(EndOfStream):
        next(g)


# ---------------------------------------------------------------------------------------
# Netconf Protocol Exceptions
# ---------------------------------------------------------------------------------------


def test_chunk_header_too_long_11():
    g = parse_messages(MockStream([b"\n#12345678901\nothing here\n##\n"]), "1.1")
    with pytest.raises(NetconfProtocolError) as excinfo:
        next(g)
    assert "Chunk header is too long (14 octets)" in str(excinfo)


def test_chunk_size_zero_11():
    g = parse_messages(MockStream([b"\n#0\n\n##\n"]), "1.1")
    with pytest.raises(NetconfProtocolError) as excinfo:
        next(g)
    assert "Length of chunk (0 octets) is out-of-range 1..4294967295" in str(excinfo)


def test_chunk_size_too_big_11():
    g = parse_messages(MockStream([b"\n#4294967296\n\n##\n"]), "1.1")
    with pytest.raises(NetconfProtocolError) as excinfo:
        next(g)
    assert "Length of chunk (4294967296 octets) is out-of-range 1..4294967295" in str(
        excinfo
    )


def test_missing_begin_of_chunks_11():
    g = parse_messages(
        MockStream([b"HERE should the header start, not here: \n#3\nFoo\n##\n"]), "1.1"
    )
    with pytest.raises(NetconfProtocolError) as excinfo:
        next(g)
    assert "Expected 'chunk-header' or 'end-of-chunks' pattern not found" in str(
        excinfo
    )


def test_unexpected_end_of_chunks_11():
    g = parse_messages(MockStream([b"\n##\n was not expected here"]), "1.1")
    with pytest.raises(NetconfProtocolError) as excinfo:
        next(g)
    assert "Unexpected 'end-of-chunks' pattern found" in str(excinfo)


def test_missing_end_of_chunks_11():
    g = parse_messages(
        MockStream([b"\n#4\nFoo HERE the next chunk or end-of-chunks was expected"]),
        "1.1",
    )
    with pytest.raises(NetconfProtocolError) as excinfo:
        next(g)
    assert "Expected 'chunk-header' or 'end-of-chunks' pattern not found" in str(
        excinfo
    )


def test_not_implemented_version():
    g = parse_messages(MockStream([b"anything"]), "3.19")
    with pytest.raises(NotImplementedError) as excinfo:
        next(g)
    assert "Unsupported message framing mode 3.19" in str(excinfo)

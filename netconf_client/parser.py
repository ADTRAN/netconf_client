import re

from netconf_client.log import logger
from netconf_client.error import NetconfProtocolError
from netconf_client.constants import (
    DELIMITER_10,
    DELIMITER_11,
    DELIMITER_10_LEN,
    DELIMITER_11_LEN,
)


def parse_messages(sock, mode):
    buf = b""
    partial_msg = []
    pos = 0
    chunk_length = 0

    while True:
        r = sock.recv(1024)
        if not r:
            return

        buf += r

        if mode == "1.0":
            (msgs, buf, pos) = parse_messages_10_from_buf(buf, pos, len(r))
        elif mode == "1.1":
            (msgs, buf, partial_msg, chunk_length) = parse_messages_11_from_buf(
                buf, partial_msg, chunk_length
            )
        else:
            raise NotImplementedError(
                "Unsupported message framing mode {}".format(mode)
            )

        for msg in msgs:
            logger.debug("Received message: %s", msg)
            new_mode = yield msg
            if new_mode is not None and new_mode != mode:
                logger.debug("Updating parsing mode to %s", new_mode)
                mode = new_mode
                pos = 0
                del partial_msg[:]
                chunk_length = 0


def parse_messages_10_from_buf(buf, pos, received):
    msgs = []

    while received:
        # `pos` trick: do not again search the part of memory that has already been searched
        index = buf.find(DELIMITER_10, pos)
        if index == -1:
            if received >= DELIMITER_10_LEN:
                pos += received - DELIMITER_10_LEN
            break

        msg = buf[:index]
        buf = buf[index + DELIMITER_10_LEN :]
        pos = 0
        received = len(buf)  # number of remaining bytes in buffer
        msgs.append(msg)

    return (msgs, buf, pos)


# RegEx matching chunk headers (version 1.1).
START_OF_CHUNK_R = re.compile(b"\n#\\d+\n")
CHUNK_R_LEN_MAX = len(b"\n#4294967295\n")  # RFC 6242


def parse_messages_11_from_buf(buf, partial_msg, chunk_length):
    msgs = []

    while buf:
        if chunk_length == 0:
            # expect a new chunk header or end-of-chunk delimiter

            # first, check for a new header
            m = START_OF_CHUNK_R.match(buf)
            if m:
                header_length = m.end() - m.start()
                if header_length > CHUNK_R_LEN_MAX:
                    raise NetconfProtocolError(
                        "Chunk header is too long ({} octets)".format(header_length)
                    )

                chunk_length = int(buf[m.start() + 2 : m.end() - 1])
                if chunk_length == 0 or chunk_length > 4294967295:
                    raise NetconfProtocolError(
                        "Length of chunk ({} octets) is out-of-range 1..4294967295".format(
                            chunk_length
                        )
                    )

                buf = buf[m.end() :]  # remove the header from buffer, keep the rest

            else:
                # check for end-of-chunk pattern
                if buf.startswith(DELIMITER_11):
                    if len(partial_msg) == 0:
                        raise NetconfProtocolError(
                            "Unexpected 'end-of-chunks' pattern found"
                        )

                    msgs.append(b"".join((partial_msg)))  # preserve a new message
                    del partial_msg[:]
                    buf = buf[
                        DELIMITER_11_LEN:
                    ]  # remove the delimiter from buffer, keep the rest

                else:
                    if len(buf) >= max(DELIMITER_11_LEN, CHUNK_R_LEN_MAX):
                        # any of them should have been found
                        raise NetconfProtocolError(
                            "Expected 'chunk-header' or 'end-of-chunks' pattern not found"
                        )
                    break  # not enough data received so far

        else:
            # expect chunk data of length `chunk_length`
            buf_length = len(buf)
            if buf_length == 0:
                break

            # copy at most `chunk_length` bytes from buffer into `partial_msg`
            available = min(buf_length, chunk_length)
            partial_msg.append(buf[:available])
            buf = buf[available:]  # remove copied bytes, keep the rest
            chunk_length -= available

    return (msgs, buf, partial_msg, chunk_length)

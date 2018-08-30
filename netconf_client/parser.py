import re

from netconf_client.log import logger
from netconf_client.constants import DELIMITER_10, DELIMITER_11


def parse_messages(sock, mode):
    buf = b""
    while True:
        r = sock.recv(1024)
        if not r:
            return
        buf += r
        if mode == "1.0":
            (msgs, buf) = parse_messages_10_from_buf(buf)
        elif mode == "1.1":
            (msgs, buf) = parse_messages_11_from_buf(buf)
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


def parse_messages_10_from_buf(buf):
    msgs = []
    while True:
        index = buf.find(DELIMITER_10)
        if index == -1:
            break
        msg = buf[:index]
        buf = buf[index + len(DELIMITER_10) :]
        msgs.append(msg)
    return (msgs, buf)


START_OF_CHUNK_R = re.compile(b"\n#(\\d+)\n")


def parse_messages_11_from_buf(buf):
    msgs = []
    partial_buf = buf
    partial_msg = b""
    while True:
        m = START_OF_CHUNK_R.match(partial_buf)

        if not m:
            break

        header_length = len(m.group(0))
        length = int(m.group(1))
        end = header_length + length

        partial_msg += partial_buf[header_length : header_length + length]
        partial_buf = partial_buf[end:]

        if partial_buf[: len(DELIMITER_11)] == DELIMITER_11:
            msgs.append(partial_msg)
            partial_msg = b""
            partial_buf = partial_buf[len(DELIMITER_11) :]
            buf = partial_buf

    return (msgs, buf)

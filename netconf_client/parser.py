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
    partial_msg = b""
    pos = 0
    chunk_length = 0

    logger.debug("WBWB: parse_messages(): Enter: mode=%s", mode)
    while True:
        try:
            r = sock.recv(1024)
        except Exception as e:
            logger.debug("WBWB: parse_messages(): Exception from sock.recv: %s", str(e))
            raise e

        logger.debug(
            "WBWB: parse_messages(): from sock.recv(): len=%d, data=<%s>",
            len(r) if r is not None else 0,
            str(r),
        )
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
                partial_msg = b""
                chunk_length = 0


def parse_messages_10_from_buf(buf, pos, received):
    msgs = []

    while received:
        logger.debug(
            "WBWB: parse_10(): LOOP: buf(%d)=<%s>, pos=%d, received=%d",
            len(buf),
            buf,
            pos,
            received,
        )

        # `pos` trick: do not again search the part of memory that has already been searched
        index = buf.find(DELIMITER_10, pos)
        if index == -1:
            if received >= DELIMITER_10_LEN:
                pos += received - DELIMITER_10_LEN
                logger.debug("WBWB: parse_10(): DELIM not found, new pos=%d", pos)
            else:
                logger.debug("WBWB: parse_10(): DELIM not found, pos unchanged")
            break

        msg = buf[:index]
        buf = buf[index + DELIMITER_10_LEN :]
        pos = 0
        received = len(buf)  # number of remaining bytes in buffer
        msgs.append(msg)
        logger.debug(
            "WBWB: parse_10(): DELIM found at %d, extracted msg(%d)=<%s>, new buf(%d)=<%s>",
            index,
            len(msg),
            msg,
            len(buf),
            buf,
        )

    logger.debug(
        "WBWB: parse_10(): RETURN %d msgs[], buf(%d)=<%s>, pos=%d",
        len(msgs),
        len(buf),
        buf,
        pos,
    )
    return (msgs, buf, pos)


# RegEx matching chunk headers (version 1.1).
START_OF_CHUNK_R = re.compile(b"\n#\\d+\n")
CHUNK_R_LEN_MAX = len(b"\n#4294967295\n")  # RFC 6242


def parse_messages_11_from_buf(buf, partial_msg, chunk_length):
    msgs = []

    while buf:
        logger.debug(
            "WBWB: parse_11(): LOOP: buf(%d)=<%s>, partial_msg(%d)=<%s>, chunk_length=%d",
            len(buf),
            buf,
            len(partial_msg),
            partial_msg,
            chunk_length,
        )

        if chunk_length == 0:
            logger.debug("WBWB: parse_11(): Handle new Chunk Header or DELIM...")
            # expect a new chunk header or end-of-chunk delimiter

            # first, check for a new header
            m = START_OF_CHUNK_R.match(buf)
            if m:
                logger.debug(
                    "WBWB: parse_11(): Chunk Header found at [%d:%d]",
                    m.start(),
                    m.end(),
                )
                header_length = m.end() - m.start()
                if header_length > CHUNK_R_LEN_MAX:
                    logger.debug(
                        "WBWB: parse_11(): PARSE ERROR: Header too long: %d => EXCEPTION!",
                        header_length,
                    )
                    raise NetconfProtocolError(
                        "Chunk header is too long ({} octets)".format(header_length)
                    )

                chunk_length = int(buf[m.start() + 2 : m.end() - 1])
                logger.debug("WBWB: parse_11(): Chunk length is: %d", chunk_length)
                if chunk_length == 0 or chunk_length > 4294967295:
                    logger.debug(
                        "WBWB: parse_11(): PARSE ERROR: Chunk length %d => EXCEPTION!",
                        chunk_length,
                    )
                    raise NetconfProtocolError(
                        "Length of chunk ({} octets) is out-of-range 1..4294967295".format(
                            chunk_length
                        )
                    )

                buf = buf[m.end() :]  # remove the header from buffer, keep the rest
                logger.debug(
                    "WBWB: parse_11(): Header removed, new buf(%d)=<%s>", len(buf), buf
                )

            else:
                # check for end-of-chunk pattern
                if buf.startswith(DELIMITER_11):
                    logger.debug(
                        "WBWB: parse_11(): DELIM found, terminating partial_msg(%d)=<%s>",
                        len(partial_msg),
                        partial_msg,
                    )

                    if len(partial_msg) == 0:
                        raise NetconfProtocolError(
                            "Unexpected 'end-of-chunks' pattern found"
                        )

                    msgs.append(partial_msg)  # preserve a new message
                    partial_msg = b""
                    buf = buf[
                        DELIMITER_11_LEN:
                    ]  # remove the delimiter from buffer, keep the rest
                    logger.debug(
                        "WBWB: parse_11(): MSG saved, new buf(%d)=<%s>", len(buf), buf
                    )

                else:
                    logger.debug("WBWB: parse_11(): DELIM NOT found")
                    if len(buf) >= max(
                        DELIMITER_11_LEN, CHUNK_R_LEN_MAX
                    ):  # any of them should have been found
                        logger.debug(
                            "WBWB: parse_11(): PARSE ERROR: Buffer is big enough (%d) but delimiter not found at begin",
                            len(buf),
                        )
                        raise NetconfProtocolError(
                            "Expected 'chunk-header' or 'end-of-chunks' pattern not found"
                        )

                    logger.debug(
                        "WBWB: parse_11(): Buffer too short (%d) to detect DELIM, need more data, break...",
                        len(buf),
                    )
                    break  # not enough data received so far

        else:
            logger.debug(
                "WBWB: parse_11(): Processing new Chunk DATA (need %d bytes)",
                chunk_length,
            )

            # expect chunk data of length `chunk_length`
            buf_length = len(buf)
            if buf_length == 0:
                logger.debug("WBWB: parse_11(): No more chunk data, break...")
                break

            # copy at most `chunk_length` bytes from buffer into `partial_msg`
            available = min(buf_length, chunk_length)
            logger.debug(
                "WBWB: parse_11(): Chunk DATA: already stored=%d, in buffer=%d, still expected=%d, available=%d",
                len(partial_msg),
                len(buf),
                chunk_length,
                available,
            )
            partial_msg += buf[:available]
            buf = buf[available:]  # remove copied bytes, keep the rest
            chunk_length -= available
            logger.debug(
                "WBWB: parse_11(): Chunk DATA saved: new partial_msg(%d)=<%s>, still missing=%d, new buf(%d)=<%s>",
                len(partial_msg),
                partial_msg,
                chunk_length,
                len(buf),
                buf,
            )

    logger.debug(
        "WBWB: parse_11(): RETURN %d msgs[], buf(%d)=<%s>, partial_msg(%d)=<%s>, chunk_length=%d",
        len(msgs),
        len(buf),
        buf,
        len(partial_msg),
        partial_msg,
        chunk_length,
    )
    return (msgs, buf, partial_msg, chunk_length)

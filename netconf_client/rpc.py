import uuid
from typing import Optional

from lxml import etree


def make_rpc(guts, msg_id=None):
    if not msg_id:
        msg_id = uuid.uuid4()

    return '<rpc message-id="{id}" xmlns="urn:ietf:params:xml:ns:netconf:base:1.0">{guts}</rpc>'.format(
        guts=guts, id=msg_id
    ).encode(
        "utf-8"
    )


def edit_config(
    config,
    target="running",
    default_operation=None,
    test_option=None,
    error_option=None,
    msg_id=None,
):
    pieces = []

    pieces.append('<edit-config xmlns:nc="urn:ietf:params:xml:ns:netconf:base:1.0">')
    pieces.append("<target><{}/></target>".format(target))
    if default_operation:
        pieces.append(
            "<default-operation>{}</default-operation>".format(default_operation)
        )
    if test_option:
        pieces.append("<test-option>{}</test-option>".format(test_option))
    if error_option:
        pieces.append("<error-option>{}</error-option>".format(error_option))
    pieces.append(config)
    pieces.append("</edit-config>")
    return make_rpc("".join(pieces), msg_id=msg_id)


def get(filter=None, with_defaults=None, msg_id=None):
    pieces = []
    pieces.append('<get xmlns:nc="urn:ietf:params:xml:ns:netconf:base:1.0">')
    if filter:
        pieces.append(filter)
    if with_defaults:
        pieces.append(make_with_defaults(with_defaults))
    pieces.append("</get>")
    return make_rpc("".join(pieces), msg_id=msg_id)


def get_config(source="running", filter=None, with_defaults=None, msg_id=None):
    pieces = []
    pieces.append('<get-config xmlns:nc="urn:ietf:params:xml:ns:netconf:base:1.0">')
    pieces.append("<source><{}/></source>".format(source))
    if filter:
        pieces.append(filter)
    if with_defaults:
        pieces.append(make_with_defaults(with_defaults))
    pieces.append("</get-config>")
    return make_rpc("".join(pieces), msg_id=msg_id)


def copy_config(target, source, filter=None, with_defaults=None, msg_id=None):
    pieces = []
    pieces.append("<copy-config>")
    pieces.append("<target><{}/></target>".format(target))
    if source.startswith("<config"):
        pieces.append("<source>{}</source>".format(source))
    else:
        pieces.append("<source><{}/></source>".format(source))
    if with_defaults:
        pieces.append(make_with_defaults(with_defaults))
    pieces.append("</copy-config>")
    return make_rpc("".join(pieces), msg_id=msg_id)


def discard_changes(msg_id=None):
    return make_rpc("<discard-changes/>", msg_id=msg_id)


def commit(
    confirmed=False, confirm_timeout=None, persist=None, persist_id=None, msg_id=None
):
    pieces = []
    pieces.append("<commit>")
    if confirmed:
        pieces.append("<confirmed/>")
    if confirm_timeout:
        pieces.append("<confirm-timeout>{}</confirm-timeout>".format(confirm_timeout))
    if persist:
        pieces.append("<persist>{}</persist>".format(persist))
    if persist_id:
        pieces.append("<persist-id>{}</persist-id>".format(persist_id))
    pieces.append("</commit>")
    return make_rpc("".join(pieces), msg_id=msg_id)


def cancel_commit(persist_id: Optional[str] = None, msg_id=None):
    pieces = []
    pieces.append("<cancel-commit>")

    if persist_id:
        pieces.append(f"<persist-id>{persist_id}</persist-id>")

    pieces.append("</cancel-commit>")
    return make_rpc("".join(pieces), msg_id=msg_id)


def lock(target, msg_id=None):
    pieces = []
    pieces.append("<lock>")
    pieces.append("<target><{}/></target>".format(target))
    pieces.append("</lock>")
    return make_rpc("".join(pieces), msg_id=msg_id)


def unlock(target, msg_id=None):
    pieces = []
    pieces.append("<unlock>")
    pieces.append("<target><{}/></target>".format(target))
    pieces.append("</unlock>")
    return make_rpc("".join(pieces), msg_id=msg_id)


def kill_session(session_id, msg_id=None):
    pieces = []
    pieces.append("<kill-session>")
    pieces.append("<session-id>{}</session-id>".format(session_id))
    pieces.append("</kill-session>")
    return make_rpc("".join(pieces), msg_id=msg_id)


def close_session(msg_id=None):
    return make_rpc("<close-session/>", msg_id=msg_id)


def create_subscription(
    stream=None, filter=None, start_time=None, stop_time=None, msg_id=None
):
    pieces = []
    pieces.append(
        '<create-subscription xmlns="urn:ietf:params:xml:ns:netconf:notification:1.0">'
    )
    if stream:
        pieces.append("<stream>{}</stream>".format(stream))
    if filter:
        pieces.append(filter)
    if start_time:
        pieces.append("<startTime>{}</startTime>".format(start_time))
    if stop_time:
        pieces.append("<stopTime>{}</stopTime>".format(stop_time))
    pieces.append("</create-subscription>")
    return make_rpc("".join(pieces), msg_id=msg_id)


def validate(source, msg_id=None):
    pieces = []
    pieces.append("<validate>")
    if etree.iselement(source):
        pieces.append(
            "<source>{}</source>".format(etree.tostring(source).decode("utf-8"))
        )
    else:
        pieces.append("<source><{}/></source>".format(source))
    pieces.append("</validate>")
    return make_rpc("".join(pieces), msg_id=msg_id)


def delete_config(target, msg_id=None):
    pieces = []
    pieces.append("<delete-config>")
    pieces.append("<target><{}/></target>".format(target))
    pieces.append("</delete-config>")
    return make_rpc("".join(pieces), msg_id=msg_id)


def make_with_defaults(with_defaults):
    return (
        '<with-defaults xmlns="urn:ietf:params:xml:ns:yang:ietf-netconf-with-defaults">'
        "{}"
        "</with-defaults>"
    ).format(with_defaults)

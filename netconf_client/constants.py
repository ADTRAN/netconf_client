DEFAULT_HELLO = b"""
  <hello xmlns="urn:ietf:params:xml:ns:netconf:base:1.0">
    <capabilities>
      <capability>urn:ietf:params:netconf:base:1.1</capability>
    </capabilities>
  </hello>
"""

CAP_NETCONF_11 = "urn:ietf:params:netconf:base:1.1"

NAMESPACES = {
    "nc": "urn:ietf:params:xml:ns:netconf:base:1.0",
    "notif": "urn:ietf:params:xml:ns:netconf:notification:1.0",
}

DELIMITER_10 = b"]]>]]>"
DELIMITER_11 = b"\n##\n"

DELIMITER_10_LEN = len(DELIMITER_10)
DELIMITER_11_LEN = len(DELIMITER_11)

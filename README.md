![Build Status](https://github.com/ADTRAN/netconf_client/workflows/CI%20Checks/badge.svg)
[![PyPI version](https://badge.fury.io/py/netconf-client.svg)](https://badge.fury.io/py/netconf-client)
[![Coverage Status](https://coveralls.io/repos/github/ADTRAN/netconf_client/badge.svg?branch=main)](https://coveralls.io/github/ADTRAN/netconf_client?branch=main)

# netconf_client

A NETCONF client for Python 3.8+.

## Basic Usage

```python
from netconf_client.connect import connect_ssh
from netconf_client.ncclient import Manager

session = connect_ssh(host="localhost", port=830, username="admin", password="password")
mgr = Manager(session, timeout=120)

mgr.edit_config(config="""<config> ... </config>""")
print(mgr.get(filter="""<filter> ... </filter>""").data_xml)
```

More complete documentation can be found in the [User Guide]

## Comparison with `ncclient`

Compared to [ncclient](https://github.com/ncclient/ncclient),
`netconf_client` has several advantages:

 - It's simpler (at the time of writing: 789 LoC vs 2889 LoC)
 - lxml can be bypassed, which can work around issues where lxml
   breaks namespaces of e.g. identityrefs
 - Support for TLS sessions

And a few disadvantages:

 - Support for non-RFC-compliant devices isn't really included in
   `netconf_client`
 - `netconf_client` does a lot less error checking and assumes you're
   sending valid messages to the server (however this can be useful
   for testing edge-case behavior of a server)


[User Guide]: https://adtran.github.io/netconf_client/

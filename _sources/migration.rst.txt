Migrating
=========

To migrate from the ``ncclient`` API to the ``netconf_client`` API you
can generally follow these two steps.

First change your imports. For example, convert from::

  from ncclient.operations import RPCError
  from ncclient.xml_ import to_ele

To this::

  from netconf_client.ncclient import RPCError, to_ele


Then you will need to migrate your connection code. For example, if
your old connection method looked like this::

    def mgr():
        from ncclient import manager, operations

        m = manager.connect_ssh(
            host="localhost",
            port=830,
            username="root",
            password="password",
            hostkey_verify=False,
            timeout=120,
        )
        m.raise_mode = operations.RaiseMode.ALL
        return m

Then your new connection code should look like this::

    def mgr():
        from netconf_client.connect import connect_ssh
        from netconf_client.ncclient import Manager

        s = connect_ssh(
            host="localhost",
            port=830,
            username="root",
            password="password",
        )
        return Manager(s, timeout=120)

As long as the existing code isn't doing anything too crazy, these
should be the only changes needed.

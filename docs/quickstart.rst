Quick Start
===========

In order to connect to a NETCONF server we can use one of the
``connect`` methods from the :mod:`netconf_client.connect` module. In
our example we will connect to a NETCONF server running over SSH, so
we will use the :func:`connect_ssh <netconf_client.connect.connect_ssh>` function.::

  from netconf_client.connect import connect_ssh

  with connect_ssh(host='192.0.2.1',
                   port=830,
                   username='admin',
                   password='password') as sesssion:
      # TODO: Do things with the session object
      pass

The object returned from any of the ``connect`` functions is a
:class:`Session <netconf_client.session.Session>` object. It acts as a
context manager, and as such it should generally be used alongside a
``with`` statement. It is importat to either use a ``with`` statement
with the object, or to manually call :meth:`Session.close
<netconf_client.session.Session.close>` in order to free the sockets
associated with the connection.

The :class:`Session <netconf_client.session.Session>` object can be
used to send and receive raw messages. However, a higher-level API is
desireable in most circumstances. For this we can use the
:class:`Manager <netconf_client.ncclient.Manager>` class.

The :class:`Manager <netconf_client.ncclient.Manager>` class is from
the :mod:`netconf_client.ncclient` module. The module overall attempts
to mimick the most common uses of the `ncclient
<https://github.com/ncclient/ncclient>`_ API (another, Open Source,
Python NETCONF client). Most of the common NETCONF operations such as
performing an ``<edit-config>`` or a ``<get>`` are implemented as
functions of this class.

In this example we will perform an ``<edit-config>`` for a single
node, and then run a ``<get-config>`` to see the change.::

  from netconf_client.connect import connect_ssh
  from netconf_client.ncclient import Manager

  with connect_ssh(host='192.0.2.1',
                   port=830,
                   username='admin',
                   password='password') as sesssion:
      mgr = Manager(session, timeout=120)
      mgr.edit_config(target='running', '''
          <config xmlns="urn:ietf:params:xml:ns:netconf:base:1.0">
            <service-alpha xmlns="http://example.com">
              <simple-string>Foo</simple-string>
            </service-alpha>
          </config>''')
      print(mgr.get_config(source='running').data_xml)

An instance of the :class:`Manager <netconf_client.ncclient.Manager>`
class should be a drop-in replacement for a manager object from
``ncclient``.

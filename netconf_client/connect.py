import socket
import ssl
from base64 import b64decode

import paramiko

from netconf_client.error import InvalidSSHHostkey
from netconf_client.session import Session
from netconf_client.log import logger


def connect_ssh(
    host=None,
    port=830,
    username="netconf",
    password=None,
    key_filename=None,
    sock=None,
    timeout=120,
    hostkey_b64=None,
):
    """Connect to a NETCONF server over SSH.

    :param str host: Hostname or IP address; unused if an already-open
                     socket is provided

    :param int port: TCP port to initiate the connection; unused if an
                     already-open socket is provided

    :param str username: Username to login with; always required

    :param str password: Password to login with; not required if a
                         private key is provided instead

    :param str key_filename: Path to an SSH private key; not required
                             if a password is provided instead

    :param sock: An already-open TCP socket; SSH will be setup on top
                 of it

    :param int timeout: Seconds to wait when connecting the socket

    :param str hostkey_b64: base64 encoded hostkey.

    :rtype: :class:`netconf_client.session.Session`

    """
    if not sock:
        sock = socket.socket()
        sock.settimeout(timeout)
        sock.connect((host, port))
        sock.settimeout(None)
    transport = paramiko.transport.Transport(sock)
    pkey = _try_load_pkey(key_filename) if key_filename else None
    hostkey = _try_load_hostkey_b64(hostkey_b64) if hostkey_b64 else None
    transport.connect(hostkey=hostkey, username=username, password=password, pkey=pkey)
    channel = transport.open_session()
    channel.invoke_subsystem("netconf")
    bundle = SshSessionSock(sock, transport, channel)
    return Session(bundle)


def connect_tls(
    host=None,
    port=6513,
    keyfile=None,
    certfile=None,
    ca_certs=None,
    sock=None,
    timeout=120,
):
    """Connect to a NETCONF server over TLS.

    :param str host: Hostname or IP address; unused if an already-open
                     socket is provided

    :param int port: TCP port to initiate the connection; unused if an
                     already-open socket is provided

    :param keyfile: Path to the key file used to identify the client

    :param certfile: Path to the certificate used to identify the client

    :param ca_certs: Path to a file containing the certificate
                     autority chains for verifying the server identity

    :param sock: An already-open TCP socket; TLS will be setup on top
                 of it

    :param int timeout: Seconds to wait when connecting the socket

    :rtype: :class:`netconf_client.session.Session`

    """
    if not sock:
        sock = socket.socket()
        sock.settimeout(timeout)
        sock.connect((host, port))
        sock.settimeout(None)
    cert_reqs = ssl.CERT_REQUIRED if ca_certs else ssl.CERT_NONE
    ssl_sock = ssl.wrap_socket(  # pylint: disable=W1505
        sock, keyfile=keyfile, certfile=certfile, cert_reqs=cert_reqs, ca_certs=ca_certs
    )
    return Session(ssl_sock)


class CallhomeManager:
    """Listener object for accepting callhome connections (:rfc:`8071`)

    Options on the listener socket (e.g. timeout) can be set on the
    ``server_socket`` member.

    This object is a context manager, and should generally be used
    within `with` statements to ensure the listening socket is
    properly closed. Note that sessions started from one of the
    `accept` functions may outlive the scope of this object and will
    not be closed automatically.

    Example of accepting a call-home connection with TLS:

    .. code-block:: python

       with CallhomeManager(port=4335) as call_home_mgr:
           session = call_home_mgr.accept_one_tls(keyfile=client_key,
                                                  certfile=client_cert,
                                                  ca_certs=ca_cert)
       with Manager(session) as mgr:
           mgr.get_config(source='running')

    """

    def __init__(self, bind_to="", port=4334, backlog=1):
        self.bind_to = bind_to
        self.port = port
        self.server_socket = None
        self.backlog = backlog

    def __enter__(self):
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.bind((self.bind_to, self.port))
        self.server_socket.listen(self.backlog)
        return self

    def accept_one(self, timeout=120):
        """Accept a single TCP client and returns it

        :param int timeout: Seconds to wait for an incoming connection

        """
        self.server_socket.settimeout(timeout)
        (sock, remote_host) = self.server_socket.accept()
        self.server_socket.settimeout(None)
        logger.info("Callhome connection initiated from remote host %s", remote_host)
        return sock

    def accept_one_ssh(self, *args, **kwds):
        """Accept a single TCP client and start an SSH session on it

        This function takes the same arguments as :func:`connect_ssh`

        """
        sock = self.accept_one(timeout=kwds.get("timeout", 120))
        kwds["sock"] = sock
        return connect_ssh(*args, **kwds)

    def accept_one_tls(self, *args, **kwds):
        """Accept a single TCP client and start a TLS session on it

        This function takes the same arguments as :func:`connect_tls`

        """
        sock = self.accept_one(timeout=kwds.get("timeout", 120))
        kwds["sock"] = sock
        return connect_tls(*args, **kwds)

    def __exit__(self, _, __, ___):
        self.server_socket.shutdown(socket.SHUT_RDWR)
        self.server_socket.close()


def _try_load_hostkey_b64(data):
    for cls in (paramiko.RSAKey, paramiko.DSSKey, paramiko.ECDSAKey):
        try:
            return cls(data=b64decode(data))
        except paramiko.SSHException:
            pass
    raise InvalidSSHHostkey()


def _try_load_pkey(path):
    for cls in (paramiko.RSAKey, paramiko.DSSKey, paramiko.ECDSAKey):
        try:
            return cls.from_private_key_file(path)
        except Exception:
            pass
    return None


class SshSessionSock:
    def __init__(self, sock, transport, channel):
        self.sock = sock
        self.transport = transport
        self.channel = channel

    def recv(self, n):
        return self.channel.recv(n)

    def sendall(self, b):
        self.channel.sendall(b)

    def close(self):
        self.channel.close()
        self.transport.close()
        self.sock.close()

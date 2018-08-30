TODO: Travis link
TODO: pypi link
TODO: rtd link

# netconf_client

A Python NETCONF client

## Basic Usage

    from netconf_client.connect import connect_ssh
    from netconf_client.ncclient import Manager
    
    session = connect_ssh(host='localhost', port=830,
                          username='admin', password='password')
    mgr = Manager(s, timeout=120)
    
    mgr.edit_config(config='''<config> ... </config>''')
    print(mgr.get(filter='''<filter>...</filter''').data_xml)

More complete documentation can be found in the User Guide

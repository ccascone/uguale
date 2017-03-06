import machine
import switch
from uconf import SWITCH, SUBNET, CLIENTS, SERVER, BN_BITRATE, SWITCH_CTRL_ADDR, SW_QUELEN, ip_addr_iterator


def gen_scripts(source_confs, duration, sw_type=switch.SW_TYPE_1FIFO):
    scripts = dict()

    num_rates_set = set([len(c['marking_rates']) for c in source_confs])
    assert len(num_rates_set) == 1, 'All users must have the same number of marking rates'

    sw_num_bands = num_rates_set.pop() + 1
    assert len(source_confs) % len(CLIENTS) == 0, 'The number of sources must be multiple of the number of clients'

    source_per_client = len(source_confs) / len(CLIENTS)
    assert len(CLIENTS) * source_per_client == len(source_confs)

    ip_addr_pool = ip_addr_iterator()
    server_ip = ip_addr_pool.next()

    source_ips = dict()
    for client in CLIENTS:
        source_ips[client] = []
        for _ in range(source_per_client):
            source_ips[client].append(ip_addr_pool.next())

    # Start switch
    sw_server_intf = SWITCH['bn_intf']
    sw_client_intfs = [i for i in SWITCH['intfs'] if i != sw_server_intf]
    client_intf_to_source_ips = {c['sw_intf']: source_ips[c] for c in CLIENTS}
    ovs_script = switch.gen_script(sw_type=sw_type, queuelen=SW_QUELEN, num_queues=sw_num_bands,
                                   client_intfs=sw_client_intfs, server_intf=sw_server_intf, server_ip=server_ip,
                                   client_intf_to_source_ips=client_intf_to_source_ips, num_bands=sw_num_bands)

    switch_script_fname = 'gen/conf-switch.sh'
    with open(switch_script_fname, 'w') as f:
        f.write('#!/usr/bin/env bash\n')
        f.write('# Switch script\n')
        f.write("\n".join(ovs_script))

    scripts[SWITCH_CTRL_ADDR] = [switch_script_fname]

    # with open('gen/testbed.sh', 'w') as f:
    #     print >> f, '#!/usr/bin/env bash\n'
    #     print >> f, 'set -e'
    #     for i in range(len(client_ips) + 1):
    #         if i == len(client_ips):
    #             machine = SERVER
    #             ip_addr = server_ip
    #         else:
    #             machine = CLIENTS[i]
    #             ip_addr = client_ips[i]
    #         client_host = machine['ctrl_addr']
    #         client_intf = machine['intf']
    #         print >> f, 'ssh %s "ifconfig %s up %s"' % (client_host, client_intf, ip_addr)

    # Start clients
    client_chain_scripts = {client['ctrl_addr']: [] for client in CLIENTS}
    per_client_source_confs = {client['ctrl_addr']: [] for client in CLIENTS}
    client_to_intfs = {client['ctrl_addr']: [] for client in CLIENTS}

    machine.reset_gloabals()

    for c in range(len(CLIENTS)):
        client = CLIENTS[c]
        client_ctrl_addr = client['ctrl_addr']
        client_intf = client['intf']

        client_to_intfs[client_ctrl_addr].append(client_intf)

        # Generate source conf for this client (add source_ip)
        client_source_confs = [dict(source_ip=ip, **source_confs.pop()) for ip in source_ips[client]]
        chain_script = machine.fwchain(source_confs=client_source_confs, server_ip=server_ip,
                                       client_intf=client_intf, client_id=client_ctrl_addr)
        client_chain_scripts[client_ctrl_addr].extend(chain_script)
        per_client_source_confs[client_ctrl_addr].extend(client_source_confs)

    for ctrl_addr, intfs in client_to_intfs.items():

        if ctrl_addr not in scripts:
            scripts[ctrl_addr] = []

        server_intfs = []
        server_script = None
        if ctrl_addr == SERVER['ctrl_addr']:
            server_intfs.append(SERVER['intf'])
            server_script = machine.gen_server_script(server_ip, SERVER['intf'])
        cleanup_script = machine.clean_up(intfs + server_intfs)
        machine_conf_fname = 'gen/conf-%s.sh' % ctrl_addr
        with open(machine_conf_fname, 'w') as f:
            f.write('#!/usr/bin/env bash\n')
            f.write('\n'.join(cleanup_script))
            f.write('\n'.join(client_chain_scripts[ctrl_addr]))
            if server_script:
                f.write('\n'.join(server_script))

        scripts[ctrl_addr].append(machine_conf_fname)

        iperf_script = machine.iperf_clients(source_confs=per_client_source_confs[ctrl_addr], server_ip=server_ip, duration=duration)
        iperf_c_fname = 'gen/iperf-c-%s.sh' % ctrl_addr
        with open(iperf_c_fname, 'w') as f:
            f.write('#!/usr/bin/env bash\n')
            f.write('\n'.join(iperf_script))

        scripts[ctrl_addr].append(iperf_c_fname)

        ping_script = machine.pingers(source_confs=per_client_source_confs[ctrl_addr], server_ip=server_ip)
        ping_fname = 'gen/ping-%s.sh' % ctrl_addr
        with open(ping_fname, 'w') as f:
            f.write('#!/usr/bin/env bash\n')
            f.write('\n'.join(ping_script))

        scripts[ctrl_addr].append(ping_fname)

    return scripts


if __name__ == '__main__':
    num_rates = 3
    rates = [i * BN_BITRATE / num_rates for i in range(1, num_rates)]
    defaults = dict(marking_rates=rates, rtt=40, num_conn=2)
    source_confs = [defaults for _ in range(len(CLIENTS) * 2)]
    gen_scripts(source_confs=source_confs, sw_type=switch.SW_TYPE_1FIFO, duration=60)

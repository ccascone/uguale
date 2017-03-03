class Hdict(dict):
    def __hash__(self):
        return hash(tuple(sorted(self.items())))


SCRIPT_ROOT = '~/uguale'

SUBNET = '192.168.200.'

SERVER = Hdict(ctrl_addr='lace', intf='enp2s0f0', sw_intf='eth6')
CLIENTS = [Hdict(ctrl_addr='lace', intf='enp2s0f1', sw_intf='eth7'),
           Hdict(ctrl_addr='mascara', intf='eth2', sw_intf='eth5'),
           Hdict(ctrl_addr='mascara', intf='eth3', sw_intf='eth3')]
SWITCH_HOSTNAME = 'whiskey'

BN_BITRATE = 10 * 10 ** 9  # 10G

# Not change this
FIRST_TCP_PORT = 5001
FIRST_UDP_PORT = 5201
MAX_PACKET_SIZE = 64 * 1024  # [Byte] maximum packet size of TCP packets [at 1Gbps]
TOKEN_RATE = 250  # [Hz] frequency of tokens update

SWITCH = dict(ctrl_addr=SWITCH_HOSTNAME, intfs=[i['sw_intf'] for i in CLIENTS + [SERVER]], bn_intf=SERVER['sw_intf'])

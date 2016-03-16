# import logging
from ryu.base import app_manager
from ryu.controller import ofp_event
from ryu.controller.handler import CONFIG_DISPATCHER,MAIN_DISPATCHER
from ryu.controller.handler import set_ev_cls
from ryu.ofproto import ofproto_v1_3

"""
dscp 1 --> queue 1
dscp 2 --> queue 2
dscp 3 --> queue 3
...
dscp N --> queue N

pc1 --->192.168.200.1 ---> [110,119]
pc2 --->192.168.200.2 ---> [120,129]
pc3 --->192.168.200.3 ---> [130,139]
"""
# LOG = logging.getLogger('app.openstate.portknock')
NETWORK_PREFIX = "192.168.200"

# HIGH PRIORITY MATCHED FIRST
RULE_PRIORITY = 10
RULE_PRIORITY_ARP = RULE_PRIORITY + 1
RULE_PRIORITY_SSH = RULE_PRIORITY - 1

PC_IDS = [1, 2, 3, 4, 98]
PORTS = [1, 2, 3, 4, 5] 
EXTERNAL_PORT = 5
HOST_IDS = [1, 2, 3]
SERVER_ID = 4
SWITCH_ID = 98
STARTING_IDS = [110, 120, 130]

IP_ETH_TYPE = 0x800
ARP_ETH_TYPE = 0x0806

MAX_NUM_BANDS = 16 # maximum number of DSCP and queues
NUM_VETHS = 10 # number of addresses for each host

EMULATED_IDS = {}

"""
Fill the EMULATED_IDS dict.
1 : [110,111,...,119]
2 : [120,121,...,129]
3 : [130,131,...,139]
"""
index_pc = 0
for pc_id in HOST_IDS:
	EMULATED_IDS[pc_id] = []
	for i in range(NUM_VETHS):
		em_id = STARTING_IDS[index_pc] + i
		EMULATED_IDS[pc_id].append(em_id)
	index_pc += 1


class FairTestApp(app_manager.RyuApp):
	OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

	def __init__(self, *args, **kwargs):
		super(FairTestApp, self).__init__(*args, **kwargs)

	@set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
	def switch_features_handler(self, ev):

		msg = ev.msg
		datapath = msg.datapath
		ofp = datapath.ofproto
		parser = datapath.ofproto_parser

		# LOG.info("Configuring switch %d..." % datapath.id)

		# --------------------- ARP RULES ------------------------#
		match = parser.OFPMatch(eth_type=ARP_ETH_TYPE)
		actions = [parser.OFPActionOutput(ofp.OFPP_FLOOD)]
		inst = [parser.OFPInstructionActions(ofp.OFPIT_APPLY_ACTIONS, actions)]
		self.add_flow(datapath=datapath, match=match, instructions=inst, priority=RULE_PRIORITY+1)

		# --------------------- REAL HOSTS ------------------------
		# Rules to let real hosts communicate
		for i_dst in range(len(PC_IDS)):
			for i_src in range(len(PC_IDS)):
				if i_dst!=i_src:
					match = parser.OFPMatch(
						eth_type=IP_ETH_TYPE,
						ipv4_src="{}.{}".format(NETWORK_PREFIX, PC_IDS[i_src]),
						ipv4_dst="{}.{}".format(NETWORK_PREFIX, PC_IDS[i_dst]))
					if PC_IDS[i_dst] == SERVER_ID:		
						actions = [parser.OFPActionSetQueue(1), parser.OFPActionOutput(PORTS[i_dst])]
					else:
						actions = [parser.OFPActionOutput(PORTS[i_dst])]
					inst = [parser.OFPInstructionActions(ofp.OFPIT_APPLY_ACTIONS, actions)]
					self.add_flow(datapath, match, instructions=inst, priority=RULE_PRIORITY)

		# --------------------- EMULATED HOSTS ------------------------#
		for pc_id in sorted(EMULATED_IDS):
			for em_id in EMULATED_IDS[pc_id]:
				# ----------- SERVER-->EMULATED ------------
				match = parser.OFPMatch(
					eth_type=IP_ETH_TYPE, 
					ipv4_src="{}.{}".format(NETWORK_PREFIX, SERVER_ID),
					ipv4_dst="{}.{}".format(NETWORK_PREFIX, em_id))
				actions = [parser.OFPActionOutput(pc_id)]
				inst = [parser.OFPInstructionActions(ofp.OFPIT_APPLY_ACTIONS, actions)]
				self.add_flow(datapath, match, instructions=inst, priority=RULE_PRIORITY)
				# ------------ EMULATED-->SERVER-------------- 
				for dscp in range(1, MAX_NUM_BANDS+1): # i=1-->8			
					match = parser.OFPMatch(
						eth_type=IP_ETH_TYPE,
						ipv4_src="{}.{}".format(NETWORK_PREFIX, em_id),
						ipv4_dst="{}.{}".format(NETWORK_PREFIX, SERVER_ID),
						ip_dscp=dscp)		
					actions = [parser.OFPActionSetQueue(dscp), parser.OFPActionOutput(SERVER_ID)]
					self.add_flow(
						datapath=datapath, 
						match=match,
						actions=actions,
						priority=RULE_PRIORITY)

		# --------------------- SSH RULES ------------------------#
		# R4 ---> OUT
		match = parser.OFPMatch(
			eth_type=IP_ETH_TYPE, 
			ipv4_src="{}.{}".format(NETWORK_PREFIX, SERVER_ID)
		)
		actions = [parser.OFPActionOutput(EXTERNAL_PORT)]
		inst = [parser.OFPInstructionActions(ofp.OFPIT_APPLY_ACTIONS, actions)]
		self.add_flow(datapath, match, 
			instructions=inst, priority=RULE_PRIORITY_SSH)

		# R4 <--- OUT
		match = parser.OFPMatch(
			eth_type=IP_ETH_TYPE, 
			in_port=EXTERNAL_PORT
		)
		actions = [parser.OFPActionOutput(SERVER_ID)]
		inst = [parser.OFPInstructionActions(ofp.OFPIT_APPLY_ACTIONS, actions)]
		self.add_flow(datapath, match, 
			instructions=inst, priority=RULE_PRIORITY_SSH)

		# SWITCH ---> OUT
		match = parser.OFPMatch(
			eth_type=IP_ETH_TYPE, 
			ipv4_dst="{}.{}".format(NETWORK_PREFIX, 200)
		)
		actions = [parser.OFPActionOutput(EXTERNAL_PORT)]
		inst = [parser.OFPInstructionActions(ofp.OFPIT_APPLY_ACTIONS, actions)]
		self.add_flow(datapath, match, 
			instructions=inst, priority=RULE_PRIORITY_SSH)

	# ----------------------------- ADD FLOW RULE --------------------------------------

	def add_flow(self, datapath, match, table_id=0, priority=0, actions=None, instructions=None):
		ofp = datapath.ofproto
		parser = datapath.ofproto_parser

		# if instructions is None , it will be apply actions --- they must be not None

		if instructions is None:
			assert len(actions)>0
			inst = [parser.OFPInstructionActions(ofp.OFPIT_WRITE_ACTIONS, actions)]
		else:
			inst = instructions

		mod = parser.OFPFlowMod(
			datapath=datapath, 
			table_id=table_id,
			priority=priority, 
			match=match, 
			instructions=inst)

		datapath.send_msg(mod)

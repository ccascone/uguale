INUTILE
# Param: host IP address

# Stop and delete ovs and veths
sh /redfox-automations/all/reset_net_conf

# Assign the correct IP address
ifconfig eth0 $1 up